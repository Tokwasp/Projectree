from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select

from data_pipeline.jobs.outbox import (
    S3ClaimCheckSqsTransport,
    _to_message,
    publish_pending_events,
)
from data_pipeline.meeting_analysis import node_updates
from data_pipeline.meeting_analysis.consumers import AnalysisCommandConsumer
from data_pipeline.meeting_analysis.contracts import (
    AnalysisCommandValidationError,
    JavaCommandParser,
    MeetingAnalysisCommandMessage,
    NodeContentBatchUpdateCommandMessage,
    NodeContentUpdateCommandMessage,
    NodeContentUpdateCommandParser,
)
from data_pipeline.meeting_analysis.node_updates import (
    process_node_content_batch_update,
    process_node_content_update,
)
from data_pipeline.meeting_analysis.persistence import CommandPayloadConflictError
from data_pipeline.pipeline.user_graph import create_user_node, user_merge_nodes
from data_pipeline.retrieval.embedding import (
    EMBEDDING_CONTRACT_VERSION,
    load_current_revision_embedding_input,
)
from data_pipeline.storage import (
    Evidence,
    GraphChangeEvent,
    GraphSnapshotArtifact,
    MeetingAnalysisCommand,
    Node,
    NodeAnalysisRun,
    NodeEmbedding,
    NodeRevision,
    NodeRevisionEvidence,
    OutboxEvent,
    ProjectGraphState,
)


PROJECT = "15"
MEETING = "35"


def _command(**changes) -> dict:
    value = {
        "commandSchemaVersion": 1,
        "commandId": str(uuid.uuid4()),
        "commandType": "NODE_CONTENT_UPDATE_REQUESTED",
        "requestedAt": "2026-08-07T01:15:00Z",
        "projectId": int(PROJECT),
        "payload": {
            "nodeId": str(uuid.uuid4()),
            "expectedNodeVersion": 1,
            "title": "사용자가 확정한 제목",
            "content": None,
            "requestedByMemberId": 15,
        },
    }
    nested = changes.pop("payload", None)
    value.update(changes)
    if nested is not None:
        value["payload"].update(nested)
    return value


def _parse(value: dict) -> NodeContentUpdateCommandMessage:
    return NodeContentUpdateCommandParser().parse(json.dumps(value))


def _batch_command(node_ids: list[tuple[uuid.UUID, int, str]], **changes) -> dict:
    value = {
        "commandSchemaVersion": 2,
        "commandId": str(uuid.uuid4()),
        "commandType": "NODE_CONTENT_UPDATE_REQUESTED",
        "requestedAt": "2026-08-09T07:30:00Z",
        "projectId": int(PROJECT),
        "payload": {
            "nodes": [
                {
                    "nodeId": str(node_id),
                    "expectedNodeVersion": version,
                    "title": title,
                }
                for node_id, version, title in node_ids
            ],
            "requestedByMemberId": 15,
        },
    }
    nested = changes.pop("payload", None)
    value.update(changes)
    if nested is not None:
        value["payload"].update(nested)
    return value


def _parse_batch(value: dict) -> NodeContentBatchUpdateCommandMessage:
    parsed = NodeContentUpdateCommandParser().parse(json.dumps(value))
    assert isinstance(parsed, NodeContentBatchUpdateCommandMessage)
    return parsed


def _seed_node(
    session_factory,
    *,
    project_id: str = PROJECT,
    graph_state: str = "ACTIVE",
    title: str = "기존 제목",
    content: str = "기존 본문",
) -> uuid.UUID:
    result = create_user_node(
        session_factory,
        project_id=project_id,
        actor_id="seed-member",
        request_id=f"seed-{uuid.uuid4()}",
        node_type="DECISION",
        category="BACKEND",
        title=title,
        content=content,
        due_date=None,
        evidence_assertion="회의에서 확인된 근거",
        external_meeting_id=MEETING,
    )
    if graph_state != "ACTIVE":
        with session_factory() as session:
            node = session.get(Node, result.node_id)
            node.graph_state = graph_state
            session.commit()
    return result.node_id


def _for_node(node_id: uuid.UUID, version: int, **changes) -> NodeContentUpdateCommandMessage:
    payload = {
        "nodeId": str(node_id),
        "expectedNodeVersion": version,
    }
    payload.update(changes.pop("payload", {}))
    return _parse(_command(payload=payload, **changes))


def test_node_update_parser_and_router_accept_strict_contract() -> None:
    value = _command()
    parsed = NodeContentUpdateCommandParser().parse(json.dumps(value))
    routed = JavaCommandParser().parse(json.dumps(value))
    assert isinstance(parsed, NodeContentUpdateCommandMessage)
    assert isinstance(routed, NodeContentUpdateCommandMessage)
    assert parsed.project_id == PROJECT
    assert parsed.requested_by_member_id == "15"

    meeting = _command(
        commandType="MEETING_ANALYSIS_REQUESTED",
        payload={
            "meetingId": 35,
            "roomName": "550e8400-e29b-41d4-a716-446655440000",
            "generateSummary": True,
            "generateNodes": True,
        },
    )
    for key in (
        "nodeId",
        "expectedNodeVersion",
        "title",
        "content",
        "requestedByMemberId",
    ):
        meeting["payload"].pop(key, None)
    assert isinstance(
        JavaCommandParser().parse(json.dumps(meeting)),
        MeetingAnalysisCommandMessage,
    )


@pytest.mark.parametrize("node_count", [1, 3])
def test_node_batch_update_parser_and_router_accept_strict_contract(
    node_count,
) -> None:
    items = [(uuid.uuid4(), index + 1, f"제목 {index}") for index in range(node_count)]
    value = _batch_command(items)
    parsed = NodeContentUpdateCommandParser().parse(json.dumps(value))
    routed = JavaCommandParser().parse(json.dumps(value))
    assert isinstance(parsed, NodeContentBatchUpdateCommandMessage)
    assert isinstance(routed, NodeContentBatchUpdateCommandMessage)
    assert parsed.project_id == PROJECT
    assert parsed.requested_by_member_id == "15"
    assert [item.node_id for item in parsed.nodes] == [item[0] for item in items]
    assert [item.title for item in parsed.nodes] == [item[2] for item in items]


def test_node_batch_update_parser_rejects_invalid_contracts() -> None:
    node_id = uuid.uuid4()
    valid = (node_id, 1, "정상 제목")
    invalid_values = [
        _batch_command([], payload={"nodes": []}),
        _batch_command([valid] * 101),
        _batch_command([valid, valid]),
        _batch_command([valid], payload={"nodes": [{"nodeId": "bad", "expectedNodeVersion": 1, "title": "제목"}]}),
        _batch_command([valid], payload={"nodes": [{"nodeId": str(node_id), "expectedNodeVersion": 0, "title": "제목"}]}),
        _batch_command([valid], payload={"nodes": [{"nodeId": str(node_id), "expectedNodeVersion": 1, "title": " "}]}),
        _batch_command(
            [valid],
            payload={
                "nodes": [
                    {
                        "nodeId": str(node_id),
                        "expectedNodeVersion": 1,
                        "title": "x" * 256,
                    }
                ]
            },
        ),
        _batch_command([valid], payload={"requestedByMemberId": "15"}),
        _batch_command(
            [valid],
            payload={
                "nodes": [
                    {
                        "nodeId": str(node_id),
                        "expectedNodeVersion": 1,
                        "title": "제목",
                        "content": "금지",
                    }
                ]
            },
        ),
    ]
    for value in invalid_values:
        with pytest.raises(AnalysisCommandValidationError):
            JavaCommandParser().parse(json.dumps(value))


@pytest.mark.parametrize(
    "changes",
    [
        {"payload": {"title": None, "content": None}},
        {"payload": {"expectedNodeVersion": 0}},
        {"payload": {"nodeId": "not-a-uuid"}},
        {"payload": {"title": " "}},
        {"payload": {"title": "x" * 256}},
        {"payload": {"content": "\t\n"}},
        {"payload": {"content": "x" * 65536}},
        {"payload": {"requestedByMemberId": "15"}},
        {"projectId": 0},
        {"commandSchemaVersion": True},
        {"commandType": "UNKNOWN"},
    ],
)
def test_node_update_parser_rejects_invalid_contract(changes) -> None:
    with pytest.raises(AnalysisCommandValidationError):
        JavaCommandParser().parse(json.dumps(_command(**changes)))


@pytest.mark.parametrize(
    ("payload", "expected_title", "expected_content"),
    [
        ({"title": "새 제목", "content": None}, "새 제목", "기존 본문"),
        ({"title": None, "content": "  새 본문  "}, "기존 제목", "  새 본문  "),
        ({"title": "새 제목", "content": "새 본문"}, "새 제목", "새 본문"),
    ],
)
@pytest.mark.parametrize("graph_state", ["ACTIVE", "UNATTACHED"])
def test_update_variants_create_revision_snapshot_and_outbox(
    session_factory,
    payload,
    expected_title,
    expected_content,
    graph_state,
) -> None:
    node_id = _seed_node(session_factory, graph_state=graph_state)
    with session_factory() as session:
        node = session.get(Node, node_id)
        before_version = node.version
        before_graph = session.get(ProjectGraphState, PROJECT).graph_version
        before_revision = node.current_revision_id
        before_source_meeting = node.source_meeting_id
        before_evidence_meetings = list(
            session.execute(
                select(Evidence.external_meeting_id)
                .join(
                    NodeRevisionEvidence,
                    NodeRevisionEvidence.evidence_id == Evidence.id,
                )
                .where(NodeRevisionEvidence.node_revision_id == before_revision)
                .order_by(Evidence.id)
            ).scalars()
        )

    command = _for_node(node_id, before_version, payload=payload)
    result = process_node_content_update(session_factory, command=command)

    assert result.status == "COMPLETED"
    assert result.changed is True
    assert result.node_version == before_version + 1
    assert result.graph_version == before_graph + 1
    with session_factory() as session:
        node = session.get(Node, node_id)
        revision = session.get(NodeRevision, node.current_revision_id)
        artifact = session.get(GraphSnapshotArtifact, result.artifact_id)
        event = session.get(OutboxEvent, result.event_id)
        assert node.title == expected_title
        assert node.content == expected_content
        assert node.current_revision_id != before_revision
        assert revision.version == node.version
        assert revision.created_by_type == "USER"
        assert revision.created_by_id == "15"
        assert node.last_actor_type == "USER"
        assert node.source_meeting_id == before_source_meeting == MEETING
        assert artifact.graph_version == result.graph_version
        assert artifact.meeting_id is None
        assert artifact.payload_json["meetingId"] is None
        assert artifact.payload_json["commandId"] == str(command.command_id)
        changed_snapshot = next(
            row for row in artifact.payload_json["nodes"] if row["nodeId"] == str(node_id)
        )
        assert changed_snapshot["sourceMeetingId"] == int(MEETING)
        assert [
            row["meetingId"]
            for row in artifact.payload_json["evidences"]
            if row["nodeId"] == str(node_id)
        ] == [
            int(value) if value is not None else None
            for value in before_evidence_meetings
        ]
        assert event.event_type == "PROJECT_GRAPH_CHANGED"
        assert event.payload["meetingId"] is None
        assert event.payload["payload"]["sourceType"] == "NODE_CONTENT_UPDATE"
        audit = session.execute(
            select(GraphChangeEvent).where(
                GraphChangeEvent.request_id == str(command.command_id)
            )
        ).scalar_one()
        assert audit.detail["actorId"] == "15"


@pytest.mark.parametrize(
    ("state", "deleted", "expected_code"),
    [
        ("MERGED", False, "MERGED_SOURCE_NOT_EDITABLE"),
        ("DELETED", True, "NODE_NOT_EDITABLE"),
        ("ARCHIVED", False, "NODE_NOT_EDITABLE"),
    ],
)
def test_noncanonical_nodes_are_rejected_without_graph_mutation(
    session_factory, state, deleted, expected_code
) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        node = session.get(Node, node_id)
        node.graph_state = state
        if state == "MERGED":
            target_id = _seed_node(session_factory)
            node.merged_into_node_id = target_id
        if deleted:
            node.deleted_at = datetime.now(timezone.utc)
        before_version = node.version
        before_graph = session.get(ProjectGraphState, PROJECT).graph_version
        session.commit()
    result = process_node_content_update(
        session_factory,
        command=_for_node(node_id, before_version),
    )
    assert result.status == "FAILED"
    assert result.failure_code == expected_code
    with session_factory() as session:
        assert session.get(Node, node_id).version == before_version
        assert session.get(ProjectGraphState, PROJECT).graph_version == before_graph
        assert session.scalar(
            select(func.count(GraphSnapshotArtifact.id)).where(
                GraphSnapshotArtifact.command_id == result.command_id
            )
        ) == 0


def test_cross_project_and_version_conflict_do_not_mutate(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        version = session.get(Node, node_id).version
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version

    cross = process_node_content_update(
        session_factory,
        command=_for_node(node_id, version, projectId=999),
    )
    conflict = process_node_content_update(
        session_factory,
        command=_for_node(node_id, version + 1),
    )
    assert cross.failure_code == "NODE_NOT_FOUND"
    assert conflict.failure_code == "NODE_VERSION_CONFLICT"
    with session_factory() as session:
        assert session.get(Node, node_id).version == version
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version


def test_full_snapshot_preserves_unmodified_nodes_and_merge_lineage(session_factory) -> None:
    target_id = _seed_node(session_factory, title="수정 대상")
    untouched_id = _seed_node(session_factory, title="그대로 둘 노드")
    source_id = _seed_node(session_factory, title="병합 원본")
    with session_factory() as session:
        source_version = session.get(Node, source_id).version
        target_version = session.get(Node, target_id).version
    merge = user_merge_nodes(
        session_factory,
        project_id=PROJECT,
        source_node_id=source_id,
        target_node_id=target_id,
        source_expected_version=source_version,
        target_expected_version=target_version,
        actor_id="seed-member",
        reason="snapshot lineage fixture",
    )
    assert merge.graph_state == "MERGED"
    with session_factory() as session:
        target_version = session.get(Node, target_id).version
        untouched = session.get(Node, untouched_id)
        untouched_state = (untouched.version, untouched.updated_at)

    result = process_node_content_update(
        session_factory,
        command=_for_node(
            target_id,
            target_version,
            payload={"title": "사용자 수정 대상", "content": None},
        ),
    )
    with session_factory() as session:
        artifact = session.get(GraphSnapshotArtifact, result.artifact_id)
        untouched = session.get(Node, untouched_id)
        assert (untouched.version, untouched.updated_at) == untouched_state
        snapshot_ids = {row["nodeId"] for row in artifact.payload_json["nodes"]}
        assert {str(target_id), str(untouched_id), str(source_id)} <= snapshot_ids
        merge_record = next(
            row
            for row in artifact.payload_json["mergeRecords"]
            if row["sourceNodeId"] == str(source_id)
        )
        assert merge_record["targetNodeId"] == str(target_id)


def test_same_value_is_noop_and_command_replay_is_exactly_once(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        node = session.get(Node, node_id)
        version = node.version
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
    noop = _for_node(
        node_id,
        version,
        payload={"title": "기존 제목", "content": "기존 본문"},
    )
    first = process_node_content_update(session_factory, command=noop)
    second = process_node_content_update(session_factory, command=noop)
    assert first.changed is second.changed is False
    assert second.replayed is True

    update = _for_node(node_id, version, payload={"title": "한 번만 반영", "content": None})
    applied = process_node_content_update(session_factory, command=update)
    replayed = process_node_content_update(session_factory, command=update)
    assert applied.changed is True
    assert replayed.replayed is True
    assert replayed.graph_version == applied.graph_version
    assert replayed.event_id == applied.event_id
    with session_factory() as session:
        assert session.get(Node, node_id).version == version + 1
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version + 1


def test_noop_keeps_ready_embedding_and_creates_no_revision(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        node = session.get(Node, node_id)
        current = load_current_revision_embedding_input(session, node=node)
        session.add(
            NodeEmbedding(
                node_id=node.id,
                embedding_version=EMBEDDING_CONTRACT_VERSION,
                embedding_model="text-embedding-3-small",
                dimension=1536,
                embedded_text_hash=current.text_hash,
                embedding=[1.0] + [0.0] * 1535,
                status="READY",
            )
        )
        version = node.version
        revision_id = node.current_revision_id
        session.commit()
    result = process_node_content_update(
        session_factory,
        command=_for_node(
            node_id,
            version,
            payload={"title": "기존 제목", "content": "기존 본문"},
        ),
    )
    assert result.changed is False
    with session_factory() as session:
        node = session.get(Node, node_id)
        embedding = session.get(
            NodeEmbedding, (node_id, EMBEDDING_CONTRACT_VERSION)
        )
        assert node.version == version
        assert node.current_revision_id == revision_id
        assert embedding.status == "READY"


def test_same_command_id_with_different_payload_is_conflict(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        version = session.get(Node, node_id).version
    first = _for_node(node_id, version, payload={"title": "첫 값", "content": None})
    process_node_content_update(session_factory, command=first)
    changed = _parse(
        _command(
            commandId=str(first.command_id),
            payload={
                "nodeId": str(node_id),
                "expectedNodeVersion": version,
                "title": "다른 값",
                "content": None,
            },
        )
    )
    with pytest.raises(CommandPayloadConflictError, match="COMMAND_ID_PAYLOAD_CONFLICT"):
        process_node_content_update(session_factory, command=changed)


def test_embedding_and_analysis_are_invalidated_atomically(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        node = session.get(Node, node_id)
        embedding_input = load_current_revision_embedding_input(session, node=node)
        embedding = NodeEmbedding(
            node_id=node.id,
            embedding_version=EMBEDDING_CONTRACT_VERSION,
            embedding_model="text-embedding-3-small",
            dimension=1536,
            embedded_text_hash=embedding_input.text_hash,
            embedding=[1.0] + [0.0] * 1535,
            status="READY",
        )
        run = NodeAnalysisRun(
            source_node_id=node.id,
            source_node_version=node.version,
            analysis_input_hash="a" * 64,
            analysis_input_hash_version="analysis-input-v2",
            retrieval_config_version="retrieval-v1",
            embedding_model="text-embedding-3-small",
            embedding_version="node-embedding-v2",
            retrieval_status="COMPLETED",
            retrieval_result_count=0,
            b_model_status="SKIPPED",
            b_model_skip_reason="NO_RETRIEVAL_CANDIDATES",
            attempt=1,
            status="RUNNING",
            requested_by="test",
        )
        session.add_all([embedding, run])
        session.flush()
        node.analysis_status = "ANALYZING"
        node.analysis_input_hash = run.analysis_input_hash
        node.current_analysis_run_id = run.id
        version = node.version
        old_embedding_hash = embedding.embedded_text_hash
        session.commit()
        run_id = run.id

    result = process_node_content_update(
        session_factory,
        command=_for_node(node_id, version, payload={"content": "의미가 바뀐 본문", "title": None}),
    )
    assert result.status == "COMPLETED"
    with session_factory() as session:
        node = session.get(Node, node_id)
        assert session.get(NodeEmbedding, (node_id, EMBEDDING_CONTRACT_VERSION)).status == "STALE"
        assert (
            load_current_revision_embedding_input(session, node=node).text_hash
            != old_embedding_hash
        )
        assert session.get(NodeAnalysisRun, run_id).status == "SUPERSEDED"
        assert node.analysis_status == "STALE"
        assert node.analysis_input_hash is None


def test_snapshot_failure_rolls_back_revision_embedding_and_versions(
    session_factory, monkeypatch
) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        node = session.get(Node, node_id)
        current = load_current_revision_embedding_input(session, node=node)
        session.add(
            NodeEmbedding(
                node_id=node.id,
                embedding_version=EMBEDDING_CONTRACT_VERSION,
                embedding_model="text-embedding-3-small",
                dimension=1536,
                embedded_text_hash=current.text_hash,
                embedding=[1.0] + [0.0] * 1535,
                status="READY",
            )
        )
        version = node.version
        revision_id = node.current_revision_id
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
        session.commit()
    command = _for_node(node_id, version)
    monkeypatch.setenv("PROJECTREE_GRAPH_SNAPSHOT_MAX_SIZE_BYTES", "1")
    result = process_node_content_update(session_factory, command=command)
    assert result.status == "FAILED"
    assert result.failure_code == "GRAPH_SNAPSHOT_TOO_LARGE"
    with session_factory() as session:
        node = session.get(Node, node_id)
        embedding = session.get(
            NodeEmbedding, (node_id, EMBEDDING_CONTRACT_VERSION)
        )
        assert node.version == version
        assert node.current_revision_id == revision_id
        assert node.title == "기존 제목"
        assert embedding.status == "READY"
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version
        assert session.scalar(
            select(func.count(MeetingAnalysisCommand.id)).where(
                MeetingAnalysisCommand.command_id == command.command_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.event_type == "NODE_CONTENT_UPDATE_REJECTED"
            )
        ) == 0


def test_batch_update_is_one_atomic_graph_mutation(session_factory) -> None:
    first_id = _seed_node(session_factory, title="첫 제목")
    second_id = _seed_node(session_factory, title="둘째 제목")
    untouched_id = _seed_node(session_factory, title="그대로")
    with session_factory() as session:
        first = session.get(Node, first_id)
        second = session.get(Node, second_id)
        untouched = session.get(Node, untouched_id)
        versions = {first_id: first.version, second_id: second.version}
        untouched_state = (untouched.version, untouched.current_revision_id)
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version

    command = _parse_batch(
        _batch_command(
            [
                (first_id, versions[first_id], "첫 제목 변경"),
                (second_id, versions[second_id], "둘째 제목 변경"),
            ]
        )
    )
    result = process_node_content_batch_update(
        session_factory, command=command
    )

    assert result.status == "COMPLETED"
    assert result.changed is True
    assert result.graph_version == graph_version + 1
    assert result.node_versions == {
        first_id: versions[first_id] + 1,
        second_id: versions[second_id] + 1,
    }
    with session_factory() as session:
        assert session.get(Node, first_id).title == "첫 제목 변경"
        assert session.get(Node, second_id).title == "둘째 제목 변경"
        untouched = session.get(Node, untouched_id)
        assert (untouched.version, untouched.current_revision_id) == untouched_state
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version + 1
        row = session.execute(
            select(MeetingAnalysisCommand).where(
                MeetingAnalysisCommand.command_id == command.command_id
            )
        ).scalar_one()
        assert row.target_node_id is None
        assert row.expected_node_version is None
        assert session.scalar(
            select(func.count(GraphChangeEvent.id)).where(
                GraphChangeEvent.request_id == str(command.command_id)
            )
        ) == 2
        assert session.scalar(
            select(func.count(GraphSnapshotArtifact.id)).where(
                GraphSnapshotArtifact.command_id == command.command_id
            )
        ) == 1
        events = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.project_id == PROJECT,
                OutboxEvent.event_type == "PROJECT_GRAPH_CHANGED",
            )
        ).scalars()
        assert sum(
            event.payload.get("commandId") == str(command.command_id)
            for event in events
        ) == 1


def test_batch_preflight_failure_mutates_no_node(session_factory) -> None:
    first_id = _seed_node(session_factory, title="첫 제목")
    second_id = _seed_node(session_factory, title="둘째 제목")
    with session_factory() as session:
        first_version = session.get(Node, first_id).version
        second_version = session.get(Node, second_id).version
        first_revision = session.get(Node, first_id).current_revision_id
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
    command = _parse_batch(
        _batch_command(
            [
                (first_id, first_version, "변경되면 안 됨"),
                (second_id, second_version + 1, "충돌"),
            ]
        )
    )

    result = process_node_content_batch_update(
        session_factory, command=command
    )

    assert result.status == "FAILED"
    assert result.failure_code == "NODE_VERSION_CONFLICT"
    assert result.failed_node_id == second_id
    with session_factory() as session:
        first = session.get(Node, first_id)
        second = session.get(Node, second_id)
        assert (first.title, first.version, first.current_revision_id) == (
            "첫 제목",
            first_version,
            first_revision,
        )
        assert (second.title, second.version) == ("둘째 제목", second_version)
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version
        assert session.scalar(
            select(func.count(GraphChangeEvent.id)).where(
                GraphChangeEvent.request_id == str(command.command_id)
            )
        ) == 0
        assert session.scalar(
            select(func.count(GraphSnapshotArtifact.id)).where(
                GraphSnapshotArtifact.command_id == command.command_id
            )
        ) == 0
        event = session.get(OutboxEvent, result.event_id)
        assert event.event_type == "NODE_CONTENT_UPDATE_REJECTED"
        assert event.payload["payload"] == {
            "sourceType": "NODE_CONTENT_UPDATE",
            "reasonCode": "NODE_VERSION_CONFLICT",
            "failedNodeId": str(second_id),
        }
        body = json.loads(_to_message(event).to_json())
        assert body == {
            "eventSchemaVersion": 3,
            "eventId": str(event.id),
            "eventType": "NODE_CONTENT_UPDATE_REJECTED",
            "occurredAt": body["occurredAt"],
            "projectId": int(PROJECT),
            "meetingId": None,
            "commandId": str(command.command_id),
            "payload": {
                "sourceType": "NODE_CONTENT_UPDATE",
                "reasonCode": "NODE_VERSION_CONFLICT",
                "failedNodeId": str(second_id),
            },
        }


def test_batch_version_conflict_precedes_same_title_noop(session_factory) -> None:
    node_id = _seed_node(session_factory, title="현재 제목")
    with session_factory() as session:
        node = session.get(Node, node_id)
        version = node.version
        revision_id = node.current_revision_id
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
    command = _parse_batch(
        _batch_command([(node_id, version + 1, "현재 제목")])
    )

    result = process_node_content_batch_update(
        session_factory, command=command
    )

    assert result.failure_code == "NODE_VERSION_CONFLICT"
    assert result.failed_node_id == node_id
    with session_factory() as session:
        node = session.get(Node, node_id)
        assert (node.version, node.current_revision_id) == (
            version,
            revision_id,
        )
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version
        assert session.scalar(
            select(func.count(GraphChangeEvent.id)).where(
                GraphChangeEvent.request_id == str(command.command_id)
            )
        ) == 0
        event = session.get(OutboxEvent, result.event_id)
        assert event.payload["payload"]["reasonCode"] == "NODE_VERSION_CONFLICT"


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("missing", "NODE_NOT_FOUND"),
        ("archived", "NODE_NOT_EDITABLE"),
        ("merged", "MERGED_SOURCE_NOT_EDITABLE"),
        ("revision", "INVALID_CURRENT_REVISION"),
    ],
)
def test_batch_rejections_are_terminal_result_events(
    session_factory, case, expected_code
) -> None:
    node_id = uuid.uuid4() if case == "missing" else _seed_node(session_factory)
    version = 1
    if case != "missing":
        with session_factory() as session:
            node = session.get(Node, node_id)
            version = node.version
            if case == "archived":
                node.graph_state = "ARCHIVED"
            elif case == "merged":
                node.graph_state = "MERGED"
                node.merged_into_node_id = _seed_node(session_factory)
            elif case == "revision":
                node.current_revision_id = None
            session.commit()
    command = _parse_batch(_batch_command([(node_id, version, "새 제목")]))

    result = process_node_content_batch_update(
        session_factory, command=command
    )

    assert result.status == "FAILED"
    assert result.failure_code == expected_code
    assert result.failed_node_id == node_id
    with session_factory() as session:
        event = session.get(OutboxEvent, result.event_id)
        assert event.event_type == "NODE_CONTENT_UPDATE_REJECTED"
        assert event.payload["payload"]["reasonCode"] == expected_code
        assert event.payload["payload"]["failedNodeId"] == str(node_id)


def test_batch_partial_noop_rejects_entire_batch(session_factory) -> None:
    noop_id = _seed_node(session_factory, title="그대로")
    changed_id = _seed_node(session_factory, title="변경 전")
    with session_factory() as session:
        noop = session.get(Node, noop_id)
        changed = session.get(Node, changed_id)
        versions = {noop_id: noop.version, changed_id: changed.version}
        revisions = {
            noop_id: noop.current_revision_id,
            changed_id: changed.current_revision_id,
        }
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
    command = _parse_batch(
        _batch_command(
            [
                (noop_id, versions[noop_id], "  그대로  "),
                (changed_id, versions[changed_id], "변경 후"),
            ]
        )
    )

    result = process_node_content_batch_update(
        session_factory, command=command
    )

    assert result.status == "FAILED"
    assert result.failure_code == "NO_CHANGE"
    assert result.failed_node_id == noop_id
    assert result.graph_version is None
    with session_factory() as session:
        noop = session.get(Node, noop_id)
        changed = session.get(Node, changed_id)
        assert (noop.title, noop.version, noop.current_revision_id) == (
            "그대로",
            versions[noop_id],
            revisions[noop_id],
        )
        assert (changed.title, changed.version, changed.current_revision_id) == (
            "변경 전",
            versions[changed_id],
            revisions[changed_id],
        )
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version
        assert session.scalar(
            select(func.count(GraphChangeEvent.id)).where(
                GraphChangeEvent.request_id == str(command.command_id)
            )
        ) == 0
        assert session.scalar(
            select(func.count(GraphSnapshotArtifact.id)).where(
                GraphSnapshotArtifact.command_id == command.command_id
            )
        ) == 0
        event = session.get(OutboxEvent, result.event_id)
        assert event.payload["payload"] == {
            "sourceType": "NODE_CONTENT_UPDATE",
            "reasonCode": "NO_CHANGE",
            "failedNodeId": str(noop_id),
        }


def test_batch_partial_noop_preserves_every_embedding(session_factory) -> None:
    changed_id = _seed_node(session_factory, title="변경 전")
    noop_id = _seed_node(session_factory, title="유지")
    with session_factory() as session:
        versions = {}
        for node_id in (changed_id, noop_id):
            node = session.get(Node, node_id)
            current = load_current_revision_embedding_input(session, node=node)
            session.add(
                NodeEmbedding(
                    node_id=node.id,
                    embedding_version=EMBEDDING_CONTRACT_VERSION,
                    embedding_model="text-embedding-3-small",
                    dimension=1536,
                    embedded_text_hash=current.text_hash,
                    embedding=[1.0] + [0.0] * 1535,
                    status="READY",
                )
            )
            versions[node_id] = node.version
        session.commit()
    command = _parse_batch(
        _batch_command(
            [
                (changed_id, versions[changed_id], "변경 후"),
                (noop_id, versions[noop_id], "유지"),
            ]
        )
    )

    result = process_node_content_batch_update(session_factory, command=command)

    assert result.failure_code == "NO_CHANGE"
    with session_factory() as session:
        assert session.get(
            NodeEmbedding, (changed_id, EMBEDDING_CONTRACT_VERSION)
        ).status == "READY"
        assert session.get(
            NodeEmbedding, (noop_id, EMBEDDING_CONTRACT_VERSION)
        ).status == "READY"


def test_batch_all_noop_rejects_once_and_replays(session_factory) -> None:
    first_id = _seed_node(session_factory, title="첫 제목")
    second_id = _seed_node(session_factory, title="둘째 제목")
    with session_factory() as session:
        versions = {
            first_id: session.get(Node, first_id).version,
            second_id: session.get(Node, second_id).version,
        }
        revisions = {
            first_id: session.get(Node, first_id).current_revision_id,
            second_id: session.get(Node, second_id).current_revision_id,
        }
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
    command = _parse_batch(
        _batch_command(
            [
                (second_id, versions[second_id], " 둘째 제목 "),
                (first_id, versions[first_id], " 첫 제목 "),
            ]
        )
    )

    first = process_node_content_batch_update(session_factory, command=command)
    replay = process_node_content_batch_update(session_factory, command=command)

    assert first.status == "FAILED"
    assert first.failure_code == "NO_CHANGE"
    assert first.failed_node_id == second_id
    assert replay.replayed is True
    assert replay.event_id == first.event_id
    assert replay.failed_node_id == second_id
    with session_factory() as session:
        for node_id in (first_id, second_id):
            node = session.get(Node, node_id)
            assert (node.version, node.current_revision_id) == (
                versions[node_id],
                revisions[node_id],
            )
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version
        assert session.scalar(
            select(func.count(GraphSnapshotArtifact.id)).where(
                GraphSnapshotArtifact.command_id == command.command_id
            )
        ) == 0
        events = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "NODE_CONTENT_UPDATE_REJECTED"
            )
        ).scalars()
        assert sum(
            event.payload.get("commandId") == str(command.command_id)
            for event in events
        ) == 1
        event = session.get(OutboxEvent, first.event_id)
        assert event.payload["payload"]["failedNodeId"] == str(second_id)


def test_batch_success_replays_and_payload_change_conflicts(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        version = session.get(Node, node_id).version
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
    raw = _batch_command([(node_id, version, "한 번만 변경")])
    command = _parse_batch(raw)

    applied = process_node_content_batch_update(session_factory, command=command)
    replay = process_node_content_batch_update(session_factory, command=command)
    changed_raw = _batch_command(
        [(node_id, version, "다른 제목")], commandId=str(command.command_id)
    )
    changed = _parse_batch(changed_raw)

    assert replay.replayed is True
    assert replay.graph_version == applied.graph_version
    assert replay.node_versions == applied.node_versions
    assert replay.event_id == applied.event_id
    with pytest.raises(
        CommandPayloadConflictError, match="COMMAND_ID_PAYLOAD_CONFLICT"
    ):
        process_node_content_batch_update(session_factory, command=changed)
    with session_factory() as session:
        assert session.get(Node, node_id).version == version + 1
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version + 1


def test_batch_snapshot_failure_rolls_back_and_rejects(session_factory, monkeypatch) -> None:
    first_id = _seed_node(session_factory, title="첫 제목")
    second_id = _seed_node(session_factory, title="둘째 제목")
    with session_factory() as session:
        versions = {
            first_id: session.get(Node, first_id).version,
            second_id: session.get(Node, second_id).version,
        }
        revisions = {
            first_id: session.get(Node, first_id).current_revision_id,
            second_id: session.get(Node, second_id).current_revision_id,
        }
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
    command = _parse_batch(
        _batch_command(
            [
                (first_id, versions[first_id], "첫 변경"),
                (second_id, versions[second_id], "둘 변경"),
            ]
        )
    )
    monkeypatch.setenv("PROJECTREE_GRAPH_SNAPSHOT_MAX_SIZE_BYTES", "1")

    result = process_node_content_batch_update(
        session_factory, command=command
    )

    assert result.status == "FAILED"
    assert result.failure_code == "GRAPH_SNAPSHOT_TOO_LARGE"
    assert result.event_id is not None
    with session_factory() as session:
        for node_id in (first_id, second_id):
            node = session.get(Node, node_id)
            assert node.version == versions[node_id]
            assert node.current_revision_id == revisions[node_id]
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version
        assert session.scalar(
            select(func.count(GraphChangeEvent.id)).where(
                GraphChangeEvent.request_id == str(command.command_id)
            )
        ) == 0
        event = session.get(OutboxEvent, result.event_id)
        assert event.payload["payload"] == {
            "sourceType": "NODE_CONTENT_UPDATE",
            "reasonCode": "GRAPH_SNAPSHOT_TOO_LARGE",
            "failedNodeId": None,
        }


class _SqsInput:
    def __init__(self, body: str):
        self.body = body
        self.deleted: list[dict] = []

    def receive_message(self, **kwargs):
        return {"Messages": [{"Body": self.body, "ReceiptHandle": "r-1", "MessageId": "m-1"}]}

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)


def test_command_consumer_dispatches_update_and_acks_after_commit(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        version = session.get(Node, node_id).version
    body = _command(payload={"nodeId": str(node_id), "expectedNodeVersion": version})
    sqs = _SqsInput(json.dumps(body))
    result = AnalysisCommandConsumer(
        sqs_client=sqs,
        queue_url="command-queue",
        session_factory=session_factory,
        wait_time_seconds=0,
    ).poll_once()
    assert result.acknowledged == 1
    assert len(sqs.deleted) == 1
    with session_factory() as session:
        assert session.get(Node, node_id).title == "사용자가 확정한 제목"


def test_command_consumer_dispatches_v2_batch_and_acks_terminal_result(
    session_factory,
) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        version = session.get(Node, node_id).version
    body = _batch_command([(node_id, version, "배치로 변경")])
    sqs = _SqsInput(json.dumps(body))

    result = AnalysisCommandConsumer(
        sqs_client=sqs,
        queue_url="command-queue",
        session_factory=session_factory,
        wait_time_seconds=0,
    ).poll_once()

    assert result.acknowledged == 1
    assert len(sqs.deleted) == 1
    with session_factory() as session:
        assert session.get(Node, node_id).title == "배치로 변경"


def test_command_consumer_acks_v2_business_rejection(session_factory) -> None:
    missing_id = uuid.uuid4()
    body = _batch_command([(missing_id, 1, "없는 노드")])
    sqs = _SqsInput(json.dumps(body))

    result = AnalysisCommandConsumer(
        sqs_client=sqs,
        queue_url="command-queue",
        session_factory=session_factory,
        wait_time_seconds=0,
    ).poll_once()

    assert result.acknowledged == 1
    assert len(sqs.deleted) == 1
    with session_factory() as session:
        command = session.execute(select(MeetingAnalysisCommand)).scalar_one()
        assert command.status == "FAILED"
        assert command.failure_code == "NODE_NOT_FOUND"
        event = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "NODE_CONTENT_UPDATE_REJECTED"
            )
        ).scalar_one()
        assert event.payload["payload"]["failedNodeId"] == str(missing_id)


def test_command_consumer_does_not_ack_v2_unexpected_failure(
    session_factory, monkeypatch
) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        version = session.get(Node, node_id).version
    body = _batch_command([(node_id, version, "변경")])
    sqs = _SqsInput(json.dumps(body))

    def explode(*args, **kwargs):
        raise RuntimeError("temporary database failure")

    monkeypatch.setattr(node_updates, "lock_project_graph_state", explode)
    result = AnalysisCommandConsumer(
        sqs_client=sqs,
        queue_url="command-queue",
        session_factory=session_factory,
        wait_time_seconds=0,
    ).poll_once()

    assert result.acknowledged == 0
    assert result.failed == 1
    assert sqs.deleted == []
    with session_factory() as session:
        assert session.scalar(
            select(func.count(MeetingAnalysisCommand.id)).where(
                MeetingAnalysisCommand.command_id
                == uuid.UUID(body["commandId"])
            )
        ) == 0


def test_command_consumer_persists_business_failure_before_ack(session_factory) -> None:
    body = _command(payload={"nodeId": str(uuid.uuid4()), "expectedNodeVersion": 1})
    sqs = _SqsInput(json.dumps(body))
    result = AnalysisCommandConsumer(
        sqs_client=sqs,
        queue_url="command-queue",
        session_factory=session_factory,
        wait_time_seconds=0,
    ).poll_once()
    assert result.acknowledged == 1
    with session_factory() as session:
        command = session.execute(select(MeetingAnalysisCommand)).scalar_one()
        assert command.status == "FAILED"
        assert command.failure_code == "NODE_NOT_FOUND"
        assert session.scalar(select(func.count(GraphSnapshotArtifact.id))) == 0
        assert session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.event_type == "NODE_CONTENT_UPDATE_REJECTED"
            )
        ) == 0


class _S3:
    def __init__(self, failures: int = 0):
        self.failures = failures
        self.puts: list[dict] = []

    def put_object(self, **kwargs):
        if self.failures:
            self.failures -= 1
            raise RuntimeError("temporary S3 failure")
        self.puts.append(kwargs)


class _ResultSqs:
    def __init__(self, failures: int = 0):
        self.failures = failures
        self.sent: list[dict] = []

    def send_message(self, **kwargs):
        if self.failures:
            self.failures -= 1
            raise RuntimeError("temporary SQS failure")
        self.sent.append(kwargs)


@pytest.mark.parametrize(("s3_failures", "sqs_failures"), [(1, 0), (0, 1)])
def test_outbox_recovery_reuses_event_and_snapshot(
    session_factory, s3_failures, sqs_failures
) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        version = session.get(Node, node_id).version
    command = _for_node(node_id, version)
    applied = process_node_content_update(session_factory, command=command)
    s3 = _S3(s3_failures)
    sqs = _ResultSqs(sqs_failures)
    transport = S3ClaimCheckSqsTransport(
        session_factory=session_factory,
        s3_client=s3,
        sqs_client=sqs,
        queue_url="result-queue",
        snapshot_bucket="snapshot-bucket",
    )
    first = publish_pending_events(
        session_factory, transport, schema_versions=("3",)
    )
    assert first.failed == 1
    with session_factory() as session:
        event = session.get(OutboxEvent, applied.event_id)
        event.available_at = datetime.now(timezone.utc)
        session.commit()
    second = publish_pending_events(
        session_factory, transport, schema_versions=("3",)
    )
    assert second.published == 1
    outgoing = json.loads(sqs.sent[0]["MessageBody"])
    assert outgoing["eventId"] == str(applied.event_id)
    assert outgoing["meetingId"] is None
    assert outgoing["payload"]["sourceType"] == "NODE_CONTENT_UPDATE"
    assert outgoing["payload"]["graphVersion"] == applied.graph_version
    assert outgoing["payload"]["snapshotRef"]["sha256"]
    replayed = process_node_content_update(session_factory, command=command)
    assert replayed.event_id == applied.event_id
    assert replayed.graph_version == applied.graph_version
    with session_factory() as session:
        assert session.scalar(
            select(func.count(GraphSnapshotArtifact.id)).where(
                GraphSnapshotArtifact.command_id == command.command_id
            )
        ) == 1
        assert session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.id == applied.event_id
            )
        ) == 1


def test_concurrent_expected_version_allows_one_update_on_postgresql(session_factory) -> None:
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL row-lock concurrency contract")
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        version = session.get(Node, node_id).version
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
    commands = [
        _for_node(node_id, version, payload={"title": f"경합-{index}", "content": None})
        for index in range(2)
    ]
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def run(command):
        try:
            barrier.wait(timeout=5)
            results.append(process_node_content_update(session_factory, command=command))
        except Exception as exc:  # pragma: no cover - assertion reports details
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(command,)) for command in commands]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert sorted((row.status, row.failure_code) for row in results) == [
        ("COMPLETED", None),
        ("FAILED", "NODE_VERSION_CONFLICT"),
    ]
    with session_factory() as session:
        assert session.get(Node, node_id).version == version + 1
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version + 1


def test_concurrent_overlapping_batches_allow_one_stale_view_on_postgresql(
    session_factory,
) -> None:
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL batch row-lock concurrency contract")
    first_id = _seed_node(session_factory, title="A")
    shared_id = _seed_node(session_factory, title="B")
    third_id = _seed_node(session_factory, title="C")
    with session_factory() as session:
        versions = {
            node_id: session.get(Node, node_id).version
            for node_id in (first_id, shared_id, third_id)
        }
        graph_version = session.get(ProjectGraphState, PROJECT).graph_version
    commands = [
        _parse_batch(
            _batch_command(
                [
                    (first_id, versions[first_id], "A1"),
                    (shared_id, versions[shared_id], "B1"),
                ]
            )
        ),
        _parse_batch(
            _batch_command(
                [
                    (shared_id, versions[shared_id], "B2"),
                    (third_id, versions[third_id], "C2"),
                ]
            )
        ),
    ]
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def run(command):
        try:
            barrier.wait(timeout=5)
            results.append(
                process_node_content_batch_update(
                    session_factory, command=command
                )
            )
        except Exception as exc:  # pragma: no cover - assertion reports details
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(command,)) for command in commands]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    assert sorted((row.status, row.failure_code) for row in results) == [
        ("COMPLETED", None),
        ("FAILED", "NODE_VERSION_CONFLICT"),
    ]
    with session_factory() as session:
        assert session.get(Node, shared_id).version == versions[shared_id] + 1
        assert session.get(ProjectGraphState, PROJECT).graph_version == graph_version + 1


def test_failed_update_leaves_no_graph_state_row_behind(session_factory) -> None:
    """The project lock row is scaffolding; a non-bumping command returns it."""

    _seed_node(session_factory)
    with session_factory() as session:
        session.delete(session.get(ProjectGraphState, PROJECT))
        session.commit()

    result = process_node_content_update(
        session_factory,
        command=_for_node(uuid.uuid4(), 1, payload={"title": "없는 노드"}),
    )

    assert result.failure_code == "NODE_NOT_FOUND"
    with session_factory() as session:
        assert session.get(ProjectGraphState, PROJECT) is None


def test_no_op_update_leaves_no_graph_state_row_behind(session_factory) -> None:
    node_id = _seed_node(session_factory, title="그대로", content="본문 그대로")
    with session_factory() as session:
        version = session.get(Node, node_id).version
        session.delete(session.get(ProjectGraphState, PROJECT))
        session.commit()

    result = process_node_content_update(
        session_factory,
        command=_for_node(
            node_id, version, payload={"title": "그대로", "content": "본문 그대로"}
        ),
    )

    assert result.status == "COMPLETED"
    assert result.changed is False
    with session_factory() as session:
        assert session.get(ProjectGraphState, PROJECT) is None
