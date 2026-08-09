"""NODE_DELETE_REQUESTED: closure, logical delete, Snapshot and Result contract."""

from __future__ import annotations

import json
import threading
import uuid

import pytest
from sqlalchemy import func, select

from data_pipeline.api.graph_services import get_project_graph_snapshot
from data_pipeline.jobs.outbox import _to_message
from data_pipeline.meeting_analysis import node_deletes
from data_pipeline.meeting_analysis.contracts import (
    AnalysisCommandValidationError,
    JavaCommandParser,
    NodeDeleteCommandMessage,
    NodeDeleteCommandParser,
)
from data_pipeline.meeting_analysis.contracts import (
    NodeContentUpdateCommandParser,
)
from data_pipeline.meeting_analysis.node_deletes import process_node_delete
from data_pipeline.meeting_analysis.node_updates import (
    process_node_content_update,
)
from data_pipeline.meeting_analysis.persistence import CommandPayloadConflictError
from data_pipeline.pipeline.user_graph import create_user_node, user_merge_nodes
from data_pipeline.storage import (
    GraphChangeEvent,
    GraphSnapshotArtifact,
    MeetingAnalysisCommand,
    MergeOperation,
    Node,
    NodeRevision,
    OutboxEvent,
    ProjectGraphState,
)


PROJECT = "15"
OTHER_PROJECT = "16"
MEETING = "35"


def _envelope(**changes) -> dict:
    value = {
        "commandSchemaVersion": 1,
        "commandId": str(uuid.uuid4()),
        "commandType": "NODE_DELETE_REQUESTED",
        "requestedAt": "2026-08-07T01:15:00Z",
        "projectId": int(PROJECT),
        "payload": {
            "nodeIds": [str(uuid.uuid4())],
            "expectedGraphVersion": 1,
            "requestedByMemberId": 15,
        },
    }
    nested = changes.pop("payload", None)
    value.update(changes)
    if nested is not None:
        value["payload"].update(nested)
    return value


def _parse(value: dict) -> NodeDeleteCommandMessage:
    return NodeDeleteCommandParser().parse(json.dumps(value))


def _delete_command(
    node_ids,
    expected_graph_version: int,
    **changes,
) -> NodeDeleteCommandMessage:
    payload = {
        "nodeIds": [str(node_id) for node_id in node_ids],
        "expectedGraphVersion": expected_graph_version,
    }
    payload.update(changes.pop("payload", {}))
    return _parse(_envelope(payload=payload, **changes))


def _seed_node(
    session_factory,
    *,
    project_id: str = PROJECT,
    title: str = "노드",
) -> uuid.UUID:
    result = create_user_node(
        session_factory,
        project_id=project_id,
        actor_id="seed-member",
        request_id=f"seed-{uuid.uuid4()}",
        node_type="DECISION",
        category="BACKEND",
        title=title,
        content="회의에서 확정한 본문",
        due_date=None,
        evidence_assertion="회의에서 확인된 근거",
        external_meeting_id=MEETING,
    )
    return result.node_id


def _attach(session_factory, *, child_id: uuid.UUID, parent_id: uuid.UUID) -> None:
    with session_factory() as session:
        session.get(Node, child_id).parent_id = parent_id
        session.commit()


def _set_state(session_factory, node_id: uuid.UUID, graph_state: str) -> None:
    with session_factory() as session:
        session.get(Node, node_id).graph_state = graph_state
        session.commit()


def _merge(session_factory, *, source_id: uuid.UUID, target_id: uuid.UUID) -> None:
    with session_factory() as session:
        source_version = session.get(Node, source_id).version
        target_version = session.get(Node, target_id).version
    user_merge_nodes(
        session_factory,
        project_id=PROJECT,
        source_node_id=source_id,
        target_node_id=target_id,
        source_expected_version=source_version,
        target_expected_version=target_version,
        actor_id="seed-member",
        reason="중복 노드 정리",
    )


def _graph_version(session_factory, project_id: str = PROJECT) -> int:
    with session_factory() as session:
        state = session.get(ProjectGraphState, project_id)
        return state.graph_version if state is not None else 0


def _node(session_factory, node_id: uuid.UUID) -> dict:
    with session_factory() as session:
        node = session.get(Node, node_id)
        return {
            "graphState": node.graph_state,
            "deletedAt": node.deleted_at,
            "deletedBy": node.deleted_by,
            "version": node.version,
            "parentId": node.parent_id,
            "mergedInto": node.merged_into_node_id,
        }


def _snapshot(session_factory, command_id: uuid.UUID) -> dict:
    with session_factory() as session:
        artifact = session.execute(
            select(GraphSnapshotArtifact).where(
                GraphSnapshotArtifact.command_id == command_id
            )
        ).scalar_one()
        return dict(artifact.payload_json)


def _update_for_node(node_id: uuid.UUID, version: int, *, title: str):
    return NodeContentUpdateCommandParser().parse(
        json.dumps(
            {
                "commandSchemaVersion": 1,
                "commandId": str(uuid.uuid4()),
                "commandType": "NODE_CONTENT_UPDATE_REQUESTED",
                "requestedAt": "2026-08-07T01:15:00Z",
                "projectId": int(PROJECT),
                "payload": {
                    "nodeId": str(node_id),
                    "expectedNodeVersion": version,
                    "title": title,
                    "content": None,
                    "requestedByMemberId": 15,
                },
            }
        )
    )


def _outbox(session_factory, event_id: uuid.UUID) -> OutboxEvent:
    with session_factory() as session:
        return session.get(OutboxEvent, event_id)


# --- contract ---------------------------------------------------------------


def test_delete_parser_and_router_accept_strict_contract() -> None:
    value = _envelope()
    parsed = NodeDeleteCommandParser().parse(json.dumps(value))
    routed = JavaCommandParser().parse(json.dumps(value))
    assert isinstance(parsed, NodeDeleteCommandMessage)
    assert isinstance(routed, NodeDeleteCommandMessage)
    assert parsed.project_id == PROJECT
    assert parsed.requested_by_member_id == "15"
    assert parsed.expected_graph_version == 1
    assert len(parsed.node_ids) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"nodeIds": []},
        {"nodeIds": "not-a-list"},
        {"nodeIds": ["not-a-uuid"]},
        {"expectedGraphVersion": -1},
        {"expectedGraphVersion": True},
        {"expectedGraphVersion": "12"},
        {"requestedByMemberId": 0},
    ],
)
def test_delete_parser_rejects_invalid_payloads(payload) -> None:
    with pytest.raises(AnalysisCommandValidationError):
        _parse(_envelope(payload=payload))


def test_delete_parser_accepts_zero_expected_graph_version() -> None:
    parsed = _parse(_envelope(payload={"expectedGraphVersion": 0}))
    assert parsed.expected_graph_version == 0


# --- happy paths ------------------------------------------------------------


def test_active_leaf_delete_bumps_node_and_graph_version(session_factory) -> None:
    node_id = _seed_node(session_factory)
    before_version = _node(session_factory, node_id)["version"]
    graph_version = _graph_version(session_factory)

    command = _delete_command([node_id], graph_version)
    result = process_node_delete(session_factory, command=command)

    assert result.status == "COMPLETED"
    assert result.deleted_node_ids == (node_id,)
    assert result.graph_version == graph_version + 1
    state = _node(session_factory, node_id)
    assert state["graphState"] == "DELETED"
    assert state["deletedAt"] is not None
    assert state["deletedBy"] == "15"
    assert state["version"] == before_version + 1
    assert _graph_version(session_factory) == graph_version + 1
    with session_factory() as session:
        # nothing is physically removed
        assert session.get(Node, node_id) is not None
        assert session.scalar(
            select(func.count(NodeRevision.id)).where(NodeRevision.node_id == node_id)
        ) >= 2


def test_parent_delete_cascades_to_every_descendant(session_factory) -> None:
    root = _seed_node(session_factory, title="A")
    child = _seed_node(session_factory, title="B")
    grandchild = _seed_node(session_factory, title="C")
    sibling = _seed_node(session_factory, title="D")
    _attach(session_factory, child_id=child, parent_id=root)
    _attach(session_factory, child_id=grandchild, parent_id=child)
    _attach(session_factory, child_id=sibling, parent_id=root)
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([root], graph_version),
    )

    assert result.status == "COMPLETED"
    assert set(result.deleted_node_ids) == {root, child, grandchild, sibling}
    for node_id in (root, child, grandchild, sibling):
        state = _node(session_factory, node_id)
        assert state["graphState"] == "DELETED"
        assert state["parentId"] is None
    # one command, one graph version step, regardless of the four Nodes
    assert _graph_version(session_factory) == graph_version + 1


def test_redundant_descendants_in_command_are_deduplicated(session_factory) -> None:
    root = _seed_node(session_factory)
    child = _seed_node(session_factory)
    _attach(session_factory, child_id=child, parent_id=root)
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([root, child, root], graph_version),
    )

    assert result.status == "COMPLETED"
    assert sorted(result.deleted_node_ids) == sorted({root, child})
    assert _graph_version(session_factory) == graph_version + 1


def test_multiple_roots_delete_each_subtree_once(session_factory) -> None:
    root_a = _seed_node(session_factory)
    child_a = _seed_node(session_factory)
    root_b = _seed_node(session_factory)
    child_b = _seed_node(session_factory)
    survivor = _seed_node(session_factory)
    _attach(session_factory, child_id=child_a, parent_id=root_a)
    _attach(session_factory, child_id=child_b, parent_id=root_b)
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([root_a, root_b], graph_version),
    )

    assert set(result.deleted_node_ids) == {root_a, child_a, root_b, child_b}
    assert len(result.deleted_node_ids) == 4
    assert _node(session_factory, survivor)["graphState"] == "ACTIVE"
    assert _graph_version(session_factory) == graph_version + 1


def test_deleting_canonical_target_deletes_its_merged_sources(session_factory) -> None:
    target = _seed_node(session_factory, title="C")
    source_a = _seed_node(session_factory, title="A")
    source_b = _seed_node(session_factory, title="B")
    _merge(session_factory, source_id=source_a, target_id=target)
    _merge(session_factory, source_id=source_b, target_id=target)
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([target], graph_version),
    )

    assert set(result.deleted_node_ids) == {target, source_a, source_b}
    for node_id in (target, source_a, source_b):
        state = _node(session_factory, node_id)
        assert state["graphState"] == "DELETED"
        assert state["mergedInto"] is None
    assert _graph_version(session_factory) == graph_version + 1


def test_reverse_merge_closure_is_transitive(session_factory) -> None:
    canonical = _seed_node(session_factory, title="C")
    middle = _seed_node(session_factory, title="B")
    leaf = _seed_node(session_factory, title="A")
    # A -> B -> C, a chain user_merge_nodes would collapse but the graph can hold.
    with session_factory() as session:
        middle_node = session.get(Node, middle)
        middle_node.graph_state = "MERGED"
        middle_node.merged_into_node_id = canonical
        leaf_node = session.get(Node, leaf)
        leaf_node.graph_state = "MERGED"
        leaf_node.merged_into_node_id = middle
        session.commit()
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([canonical], graph_version),
    )

    assert set(result.deleted_node_ids) == {canonical, middle, leaf}


def test_deleting_a_merged_source_keeps_its_canonical_target(session_factory) -> None:
    target = _seed_node(session_factory, title="C")
    source = _seed_node(session_factory, title="A")
    _merge(session_factory, source_id=source, target_id=target)
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([source], graph_version),
    )

    assert result.deleted_node_ids == (source,)
    assert _node(session_factory, source)["graphState"] == "DELETED"
    assert _node(session_factory, target)["graphState"] == "ACTIVE"


def test_unattached_node_is_deletable(session_factory) -> None:
    node_id = _seed_node(session_factory)
    _set_state(session_factory, node_id, "UNATTACHED")
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([node_id], graph_version),
    )

    assert result.status == "COMPLETED"
    assert _node(session_factory, node_id)["graphState"] == "DELETED"


# --- business rejections ----------------------------------------------------


def test_graph_version_conflict_rejects_without_mutating(session_factory) -> None:
    node_id = _seed_node(session_factory)
    graph_version = _graph_version(session_factory)
    node_version = _node(session_factory, node_id)["version"]

    result = process_node_delete(
        session_factory,
        command=_delete_command([node_id], graph_version + 7),
    )

    assert result.status == "FAILED"
    assert result.failure_code == "GRAPH_VERSION_CONFLICT"
    assert _graph_version(session_factory) == graph_version
    state = _node(session_factory, node_id)
    assert state["graphState"] == "ACTIVE"
    assert state["version"] == node_version
    with session_factory() as session:
        assert session.scalar(
            select(func.count(GraphSnapshotArtifact.id)).where(
                GraphSnapshotArtifact.command_id == result.command_id
            )
        ) == 0
    event = _outbox(session_factory, result.event_id)
    assert event.event_type == "NODE_DELETE_REJECTED"
    assert event.payload["meetingId"] is None
    assert event.payload["payload"]["sourceType"] == "NODE_DELETE"
    assert event.payload["payload"] == {
        "sourceType": "NODE_DELETE",
        "reasonCode": "GRAPH_VERSION_CONFLICT",
    }


def test_missing_node_is_rejected_as_node_not_found(session_factory) -> None:
    graph_version = _graph_version(session_factory)
    result = process_node_delete(
        session_factory,
        command=_delete_command([uuid.uuid4()], graph_version),
    )
    assert result.failure_code == "NODE_NOT_FOUND"
    assert _graph_version(session_factory) == graph_version
    assert _outbox(session_factory, result.event_id).event_type == "NODE_DELETE_REJECTED"


def test_already_deleted_node_is_rejected_as_node_not_found(session_factory) -> None:
    node_id = _seed_node(session_factory)
    graph_version = _graph_version(session_factory)
    process_node_delete(
        session_factory,
        command=_delete_command([node_id], graph_version),
    )
    result = process_node_delete(
        session_factory,
        command=_delete_command([node_id], graph_version + 1),
    )
    assert result.failure_code == "NODE_NOT_FOUND"


def test_foreign_project_node_is_rejected_as_project_mismatch(session_factory) -> None:
    foreign_id = _seed_node(session_factory, project_id=OTHER_PROJECT)
    mine = _seed_node(session_factory)
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([mine, foreign_id], graph_version),
    )

    assert result.failure_code == "NODE_PROJECT_MISMATCH"
    assert _node(session_factory, foreign_id)["graphState"] == "ACTIVE"
    assert _node(session_factory, mine)["graphState"] == "ACTIVE"
    payload = _outbox(session_factory, result.event_id).payload["payload"]
    assert payload == {
        "sourceType": "NODE_DELETE",
        "reasonCode": "NODE_PROJECT_MISMATCH",
    }


# --- idempotency ------------------------------------------------------------


def test_same_command_id_and_payload_replays_without_redeleting(session_factory) -> None:
    root = _seed_node(session_factory)
    child = _seed_node(session_factory)
    _attach(session_factory, child_id=child, parent_id=root)
    graph_version = _graph_version(session_factory)
    command = _delete_command([root], graph_version)

    applied = process_node_delete(session_factory, command=command)
    versions = {
        node_id: _node(session_factory, node_id)["version"] for node_id in (root, child)
    }

    replayed = process_node_delete(session_factory, command=command)

    assert replayed.replayed is True
    assert replayed.status == "COMPLETED"
    assert replayed.graph_version == applied.graph_version
    assert replayed.event_id == applied.event_id
    assert replayed.artifact_id == applied.artifact_id
    assert set(replayed.deleted_node_ids) == set(applied.deleted_node_ids)
    assert _graph_version(session_factory) == graph_version + 1
    for node_id, version in versions.items():
        assert _node(session_factory, node_id)["version"] == version
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


def test_rejection_replay_reuses_the_same_result_event(session_factory) -> None:
    node_id = _seed_node(session_factory)
    graph_version = _graph_version(session_factory)
    command = _delete_command([node_id], graph_version + 5)

    rejected = process_node_delete(session_factory, command=command)
    replayed = process_node_delete(session_factory, command=command)

    assert replayed.status == "FAILED"
    assert replayed.failure_code == "GRAPH_VERSION_CONFLICT"
    assert replayed.event_id == rejected.event_id
    with session_factory() as session:
        assert session.scalar(
            select(func.count(OutboxEvent.id)).where(
                OutboxEvent.event_type == "NODE_DELETE_REJECTED"
            )
        ) == 1


def test_same_command_id_with_a_different_payload_conflicts(session_factory) -> None:
    first = _seed_node(session_factory)
    second = _seed_node(session_factory)
    graph_version = _graph_version(session_factory)
    command = _delete_command([first], graph_version)
    process_node_delete(session_factory, command=command)

    reused = NodeDeleteCommandMessage(
        command_id=command.command_id,
        project_id=command.project_id,
        node_ids=(second,),
        expected_graph_version=command.expected_graph_version,
        requested_by_member_id=command.requested_by_member_id,
        requested_at=command.requested_at,
    )
    with pytest.raises(CommandPayloadConflictError):
        process_node_delete(session_factory, command=reused)

    assert _node(session_factory, second)["graphState"] == "ACTIVE"
    assert _graph_version(session_factory) == graph_version + 1


def test_seed_order_is_part_of_the_payload_identity(session_factory) -> None:
    first = _seed_node(session_factory)
    second = _seed_node(session_factory)
    graph_version = _graph_version(session_factory)
    command = _delete_command([first, second], graph_version)
    process_node_delete(session_factory, command=command)

    reordered = NodeDeleteCommandMessage(
        command_id=command.command_id,
        project_id=command.project_id,
        node_ids=(second, first),
        expected_graph_version=command.expected_graph_version,
        requested_by_member_id=command.requested_by_member_id,
        requested_at=command.requested_at,
    )
    with pytest.raises(CommandPayloadConflictError):
        process_node_delete(session_factory, command=reordered)


# --- durability -------------------------------------------------------------


def test_failure_inside_the_transaction_rolls_everything_back(
    session_factory, monkeypatch
) -> None:
    root = _seed_node(session_factory)
    child = _seed_node(session_factory)
    _attach(session_factory, child_id=child, parent_id=root)
    graph_version = _graph_version(session_factory)
    versions = {
        node_id: _node(session_factory, node_id)["version"] for node_id in (root, child)
    }

    def explode(*args, **kwargs):
        raise RuntimeError("snapshot staging failed")

    monkeypatch.setattr(node_deletes, "stage_project_graph_changed_v3", explode)
    command = _delete_command([root], graph_version)
    with pytest.raises(RuntimeError):
        process_node_delete(session_factory, command=command)

    assert _graph_version(session_factory) == graph_version
    for node_id, version in versions.items():
        state = _node(session_factory, node_id)
        assert state["graphState"] == "ACTIVE"
        assert state["deletedAt"] is None
        assert state["version"] == version
    with session_factory() as session:
        assert session.scalar(
            select(func.count(MeetingAnalysisCommand.id)).where(
                MeetingAnalysisCommand.command_id == command.command_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(GraphSnapshotArtifact.id)).where(
                GraphSnapshotArtifact.command_id == command.command_id
            )
        ) == 0
        assert session.scalar(
            select(func.count(GraphChangeEvent.id)).where(
                GraphChangeEvent.request_id == str(command.command_id)
            )
        ) == 0


# --- snapshot and result contract -------------------------------------------


def test_success_snapshot_and_result_event_contract(session_factory) -> None:
    root = _seed_node(session_factory, title="A")
    child = _seed_node(session_factory, title="B")
    merged_source = _seed_node(session_factory, title="M")
    survivor = _seed_node(session_factory, title="S")
    _attach(session_factory, child_id=child, parent_id=root)
    _merge(session_factory, source_id=merged_source, target_id=root)
    graph_version = _graph_version(session_factory)

    command = _delete_command([root], graph_version)
    result = process_node_delete(session_factory, command=command)

    deleted = set(result.deleted_node_ids)
    assert deleted == {root, child, merged_source}
    snapshot = _snapshot(session_factory, command.command_id)
    node_ids = {row["nodeId"] for row in snapshot["nodes"]}
    assert node_ids == {str(survivor)}
    assert not (node_ids & {str(node_id) for node_id in deleted})
    assert all(
        row["nodeId"] not in {str(node_id) for node_id in deleted}
        for row in snapshot["evidences"]
    )
    assert all(
        row["sourceNodeId"] not in {str(node_id) for node_id in deleted}
        for row in snapshot["mergeRecords"]
    )
    for row in snapshot["nodes"]:
        assert row["parentNodeId"] not in {str(node_id) for node_id in deleted}
        assert row["mergedIntoNodeId"] not in {str(node_id) for node_id in deleted}
    assert snapshot["graphVersion"] == graph_version + 1
    assert snapshot["meetingId"] is None
    assert snapshot["commandId"] == str(command.command_id)

    event = _outbox(session_factory, result.event_id)
    assert event.event_type == "PROJECT_GRAPH_CHANGED"
    assert event.schema_version == "3"
    assert event.payload["meetingId"] is None
    assert event.payload["commandId"] == str(command.command_id)
    assert event.payload["payload"]["sourceType"] == "NODE_DELETE"
    assert event.payload["payload"]["graphVersion"] == graph_version + 1
    assert event.payload["payload"]["snapshotArtifactId"] == str(result.artifact_id)

    with session_factory() as session:
        # merge history is preserved; only the Snapshot filters it out
        assert session.scalar(
            select(func.count(MergeOperation.id)).where(
                MergeOperation.source_node_id == merged_source
            )
        ) == 1


def test_command_row_records_the_delete_outcome(session_factory) -> None:
    node_id = _seed_node(session_factory)
    graph_version = _graph_version(session_factory)
    command = _delete_command([node_id], graph_version)
    process_node_delete(session_factory, command=command)

    with session_factory() as session:
        row = session.execute(
            select(MeetingAnalysisCommand).where(
                MeetingAnalysisCommand.command_id == command.command_id
            )
        ).scalar_one()
        assert row.command_type == "NODE_DELETE_REQUESTED"
        assert row.status == "COMPLETED"
        assert row.expected_graph_version == graph_version
        assert row.expected_node_version is None
        assert row.target_node_id is None
        assert row.meeting_id is None
        assert row.requested_by_member_id == "15"


# --- concurrency ------------------------------------------------------------


def test_concurrent_expected_graph_version_allows_one_delete_on_postgresql(
    session_factory,
) -> None:
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL row-lock concurrency contract")
    first = _seed_node(session_factory)
    second = _seed_node(session_factory)
    graph_version = _graph_version(session_factory)
    commands = [
        _delete_command([node_id], graph_version) for node_id in (first, second)
    ]
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def run(command):
        try:
            barrier.wait(timeout=5)
            results.append(process_node_delete(session_factory, command=command))
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
        ("FAILED", "GRAPH_VERSION_CONFLICT"),
    ]
    assert _graph_version(session_factory) == graph_version + 1
    states = [_node(session_factory, node_id)["graphState"] for node_id in (first, second)]
    assert sorted(states) == ["ACTIVE", "DELETED"]


def test_delete_on_a_project_without_a_graph_state_row(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        session.delete(session.get(ProjectGraphState, PROJECT))
        session.commit()

    result = process_node_delete(
        session_factory,
        command=_delete_command([node_id], 0),
    )

    assert result.status == "COMPLETED"
    assert result.graph_version == 1
    assert _graph_version(session_factory) == 1


def test_excluded_child_of_a_deleted_parent_does_not_block_the_delete(
    session_factory,
) -> None:
    root = _seed_node(session_factory)
    excluded = _seed_node(session_factory)
    _attach(session_factory, child_id=excluded, parent_id=root)
    # EXCLUDED/ARCHIVED Nodes keep their historical parent pointer by design and
    # never reach the Snapshot, so they are neither deleted nor treated as a
    # dangling reference.
    _set_state(session_factory, excluded, "EXCLUDED")
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([root], graph_version),
    )

    assert result.status == "COMPLETED"
    assert result.deleted_node_ids == (root,)
    survivor = _node(session_factory, excluded)
    assert survivor["graphState"] == "EXCLUDED"
    assert survivor["parentId"] == root
    snapshot = _snapshot(session_factory, result.command_id)
    assert {row["nodeId"] for row in snapshot["nodes"]} == set()


# --- rejection Result payload contract --------------------------------------


@pytest.mark.parametrize(
    "reason_code",
    ["GRAPH_VERSION_CONFLICT", "NODE_NOT_FOUND", "NODE_PROJECT_MISMATCH"],
)
def test_rejection_payload_carries_only_source_type_and_reason_code(
    session_factory, reason_code
) -> None:
    graph_version = _graph_version(session_factory)
    if reason_code == "GRAPH_VERSION_CONFLICT":
        node_id = _seed_node(session_factory)
        graph_version = _graph_version(session_factory)
        command = _delete_command([node_id], graph_version + 3)
    elif reason_code == "NODE_NOT_FOUND":
        _seed_node(session_factory)
        graph_version = _graph_version(session_factory)
        command = _delete_command([uuid.uuid4()], graph_version)
    else:
        foreign = _seed_node(session_factory, project_id=OTHER_PROJECT)
        graph_version = _graph_version(session_factory)
        command = _delete_command([foreign], graph_version)

    result = process_node_delete(session_factory, command=command)

    assert result.failure_code == reason_code
    payload = _outbox(session_factory, result.event_id).payload["payload"]
    assert payload == {"sourceType": "NODE_DELETE", "reasonCode": reason_code}
    assert "reason" not in payload
    assert "nodeIds" not in payload
    assert "expectedGraphVersion" not in payload
    assert "currentGraphVersion" not in payload


def test_rejection_wire_body_matches_the_java_contract(session_factory) -> None:
    node_id = _seed_node(session_factory)
    graph_version = _graph_version(session_factory)
    result = process_node_delete(
        session_factory,
        command=_delete_command([node_id], graph_version + 4),
    )

    body = json.loads(_to_message(_outbox(session_factory, result.event_id)).to_json())

    assert body["eventSchemaVersion"] == 3
    assert body["eventType"] == "NODE_DELETE_REJECTED"
    assert body["meetingId"] is None
    assert body["projectId"] == int(PROJECT)
    assert body["payload"] == {
        "sourceType": "NODE_DELETE",
        "reasonCode": "GRAPH_VERSION_CONFLICT",
    }
    assert set(body) == {
        "eventSchemaVersion",
        "eventId",
        "eventType",
        "occurredAt",
        "projectId",
        "meetingId",
        "commandId",
        "payload",
    }


# --- transient graph state row ----------------------------------------------


def _forget_graph_state(session_factory) -> None:
    with session_factory() as session:
        state = session.get(ProjectGraphState, PROJECT)
        if state is not None:
            session.delete(state)
            session.commit()


def test_rejection_leaves_no_graph_state_row_behind(session_factory) -> None:
    """A project with no row must still have no row after a rejection."""

    _seed_node(session_factory)
    _forget_graph_state(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([uuid.uuid4()], 0),
    )

    assert result.failure_code == "NODE_NOT_FOUND"
    with session_factory() as session:
        assert session.get(ProjectGraphState, PROJECT) is None


@pytest.mark.parametrize(
    "reason_code", ["GRAPH_VERSION_CONFLICT", "NODE_PROJECT_MISMATCH"]
)
def test_other_rejections_also_leave_no_graph_state_row(
    session_factory, reason_code
) -> None:
    if reason_code == "GRAPH_VERSION_CONFLICT":
        node_id = _seed_node(session_factory)
        _forget_graph_state(session_factory)
        command = _delete_command([node_id], 9)
    else:
        foreign = _seed_node(session_factory, project_id=OTHER_PROJECT)
        _forget_graph_state(session_factory)
        command = _delete_command([foreign], 0)

    result = process_node_delete(session_factory, command=command)

    assert result.failure_code == reason_code
    with session_factory() as session:
        assert session.get(ProjectGraphState, PROJECT) is None


def test_rejection_never_touches_an_existing_graph_state_row(session_factory) -> None:
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        before = session.get(ProjectGraphState, PROJECT)
        version, updated_at = before.graph_version, before.updated_at

    result = process_node_delete(
        session_factory,
        command=_delete_command([node_id], version + 6),
    )

    assert result.failure_code == "GRAPH_VERSION_CONFLICT"
    with session_factory() as session:
        after = session.get(ProjectGraphState, PROJECT)
        assert after is not None
        assert after.graph_version == version
        assert after.updated_at == updated_at


def test_rejection_on_a_project_at_version_zero_keeps_snapshot_api_absent(
    session_factory,
) -> None:
    """The graph-snapshot API must keep answering "no graph" (404)."""

    _forget_graph_state(session_factory)
    assert get_project_graph_snapshot(session_factory, project_id=PROJECT) is None

    result = process_node_delete(
        session_factory,
        command=_delete_command([uuid.uuid4()], 0),
    )

    assert result.failure_code == "NODE_NOT_FOUND"
    assert get_project_graph_snapshot(session_factory, project_id=PROJECT) is None


# --- legacy Nodes without a Revision -----------------------------------------


def test_delete_advances_node_version_for_a_node_without_a_revision(
    session_factory,
) -> None:
    """A legacy projection has no Revision to derive the next version from."""

    node_id = _seed_node(session_factory)
    with session_factory() as session:
        node = session.get(Node, node_id)
        node.current_revision_id = None
        session.commit()
        before_version = node.version
    graph_version = _graph_version(session_factory)

    result = process_node_delete(
        session_factory,
        command=_delete_command([node_id], graph_version),
    )

    assert result.status == "COMPLETED"
    state = _node(session_factory, node_id)
    assert state["graphState"] == "DELETED"
    assert state["version"] == before_version + 1
    assert result.node_versions[node_id] == before_version + 1
    assert _graph_version(session_factory) == graph_version + 1


# --- snapshot retention ------------------------------------------------------


def test_snapshot_keeps_surviving_merged_unattached_and_merge_records(
    session_factory,
) -> None:
    """Only the deleted subtree leaves the Snapshot; the rest is untouched."""

    kept_target = _seed_node(session_factory, title="T")
    kept_source = _seed_node(session_factory, title="S")
    doomed_target = _seed_node(session_factory, title="T2")
    doomed_source = _seed_node(session_factory, title="S2")
    unattached = _seed_node(session_factory, title="U")
    _merge(session_factory, source_id=kept_source, target_id=kept_target)
    _merge(session_factory, source_id=doomed_source, target_id=doomed_target)
    _set_state(session_factory, unattached, "UNATTACHED")
    graph_version = _graph_version(session_factory)

    command = _delete_command([doomed_target], graph_version)
    result = process_node_delete(session_factory, command=command)

    assert set(result.deleted_node_ids) == {doomed_target, doomed_source}
    snapshot = _snapshot(session_factory, command.command_id)

    states = {row["nodeId"]: row["graphState"] for row in snapshot["nodes"]}
    assert states == {
        str(kept_target): "ACTIVE",
        str(kept_source): "MERGED",
        str(unattached): "UNATTACHED",
    }
    # the surviving MERGED source still points at its canonical target
    kept_row = next(
        row for row in snapshot["nodes"] if row["nodeId"] == str(kept_source)
    )
    assert kept_row["mergedIntoNodeId"] == str(kept_target)

    # mergeRecords is non-empty AND correctly filtered: the surviving merge
    # stays, the merge whose source was deleted is gone.
    assert [
        (row["sourceNodeId"], row["targetNodeId"]) for row in snapshot["mergeRecords"]
    ] == [(str(kept_source), str(kept_target))]

    # evidence of surviving Nodes is retained, deleted Nodes contribute none
    evidence_nodes = {row["nodeId"] for row in snapshot["evidences"]}
    assert evidence_nodes == {str(kept_target), str(kept_source), str(unattached)}


def test_concurrent_update_and_delete_do_not_deadlock_on_postgresql(
    session_factory,
) -> None:
    """Both commands take the project lock before any Node lock.

    Without that shared order the update holds the Node and waits for the graph
    version row while the delete holds the graph version row and waits for the
    Node, which PostgreSQL resolves by aborting one side with a deadlock error.
    """

    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("PostgreSQL row-lock ordering contract")
    node_id = _seed_node(session_factory)
    with session_factory() as session:
        node_version = session.get(Node, node_id).version
    graph_version = _graph_version(session_factory)

    delete_command = _delete_command([node_id], graph_version)
    update_command = _update_for_node(node_id, node_version, title="동시 수정")

    barrier = threading.Barrier(2)
    outcomes: dict[str, object] = {}
    errors = []

    def run(name, call, command):
        try:
            barrier.wait(timeout=5)
            outcomes[name] = call(session_factory, command=command)
        except Exception as exc:  # pragma: no cover - assertion reports details
            errors.append((name, exc))

    threads = [
        threading.Thread(target=run, args=("delete", process_node_delete, delete_command)),
        threading.Thread(
            target=run, args=("update", process_node_content_update, update_command)
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)

    assert not errors, errors
    assert all(not thread.is_alive() for thread in threads)

    pair = (
        (outcomes["delete"].status, outcomes["delete"].failure_code),
        (outcomes["update"].status, outcomes["update"].failure_code),
    )
    # Exactly two serializations are valid. Delete first: the Node is gone, so
    # the update finds it not editable. Update first: it bumped the version the
    # delete expected, so the delete conflicts.
    assert pair in {
        (("COMPLETED", None), ("FAILED", "NODE_NOT_EDITABLE")),
        (("FAILED", "GRAPH_VERSION_CONFLICT"), ("COMPLETED", None)),
    }, pair
    # whichever won, the project advanced exactly one graph version
    assert _graph_version(session_factory) == graph_version + 1
