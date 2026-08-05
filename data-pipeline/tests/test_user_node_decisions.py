"""FastAPI-to-database tests for recommendation-independent user decisions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION
from data_pipeline.api.app import create_app
from data_pipeline.api.dependencies import get_session_factory
from data_pipeline.storage import (
    AnalysisCandidate,
    AnalysisJob,
    BModelResult,
    GraphChangeEvent,
    Node,
    NodeAnalysisRun,
    NodeMergeHistory,
    OutboxEvent,
    Relation,
)

PROJECT = "proj-manual-decision"
HEADERS = {"X-Project-Id": PROJECT, "X-Actor-Id": "manual-reviewer"}


@pytest.fixture()
def client(session_factory):
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _node(
    session_factory,
    *,
    project_id: str = PROJECT,
    graph_state: str = "UNATTACHED",
    node_type: str = "DECISION",
    meeting_id: str | None = None,
) -> tuple[uuid.UUID, int]:
    with session_factory() as session:
        value = Node(
            project_id=project_id,
            source_meeting_id=meeting_id or f"meeting-{uuid.uuid4()}",
            source_item_id=f"item-{uuid.uuid4()}",
            node_type=node_type,
            category="BACKEND",
            title=f"{node_type} title",
            content=f"{node_type} content",
            graph_state=graph_state,
            analysis_status="PENDING",
        )
        session.add(value)
        session.commit()
        return value.id, value.version


def _run(
    session_factory,
    source_id: uuid.UUID,
    *,
    outcome: str,
) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        source = session.get(Node, source_id)
        input_hash = uuid.uuid4().hex * 2
        if outcome == "SKIPPED":
            run_status = "COMPLETED"
            node_status = "ANALYZED"
            b_status = "SKIPPED"
            skip_reason = "NO_RETRIEVAL_CANDIDATES"
            failure_code = None
        elif outcome == "FAILED":
            run_status = "FAILED"
            node_status = "FAILED"
            b_status = "FAILED"
            skip_reason = None
            failure_code = "B_MODEL_FAILED"
        else:
            run_status = "PENDING"
            node_status = "PENDING"
            b_status = "PENDING"
            skip_reason = None
            failure_code = None
        run = NodeAnalysisRun(
            source_node_id=source.id,
            source_node_version=source.version,
            analysis_input_hash=input_hash,
            analysis_input_hash_version="analysis-input-v2",
            retrieval_config_version="retrieval-test-v1",
            embedding_model="text-embedding-3-small",
            embedding_version=EMBEDDING_CONTRACT_VERSION,
            retrieval_status=(
                "COMPLETED" if outcome in {"SKIPPED", "FAILED"} else "PENDING"
            ),
            retrieval_result_count=(
                0 if outcome in {"SKIPPED", "FAILED"} else None
            ),
            retrieval_completed_at=(
                now if outcome in {"SKIPPED", "FAILED"} else None
            ),
            b_model_status=b_status,
            b_model_skip_reason=skip_reason,
            b_model_failure_code=failure_code,
            b_model_completed_at=(
                now if outcome in {"SKIPPED", "FAILED"} else None
            ),
            attempt=1,
            status=run_status,
            requested_by="test",
            failure_code=failure_code,
            completed_at=(
                now if outcome in {"SKIPPED", "FAILED"} else None
            ),
        )
        session.add(run)
        session.flush()
        source.current_analysis_run_id = run.id
        source.analysis_input_hash = input_hash
        source.analysis_status = node_status
        session.commit()
        return run.id


def _recommendation(
    session_factory,
    *,
    source_id: uuid.UUID,
    run_id: uuid.UUID,
    recommendation: str,
    target_id: uuid.UUID | None = None,
    relation_type: str | None = None,
) -> uuid.UUID:
    with session_factory() as session:
        source = session.get(Node, source_id)
        target = session.get(Node, target_id) if target_id else None
        run = session.get(NodeAnalysisRun, run_id)
        run.b_model_status = "SUCCEEDED"
        run.b_model_skip_reason = None
        run.b_model_completed_at = datetime.now(timezone.utc)
        result = BModelResult(
            project_id=PROJECT,
            analysis_run_id=run_id,
            source_node_id=source.id,
            source_node_version=source.version,
            recommendation=recommendation,
            target_node_id=target.id if target else None,
            target_node_version=target.version if target else None,
            relation_type=relation_type,
            suggested_title="recommended title",
            suggested_content="recommended content",
            reason="test recommendation",
            model="fake-b",
            model_version="v1",
            metadata_json={},
            validation_status="VALIDATED",
        )
        session.add(result)
        session.flush()
        candidate = AnalysisCandidate(
            project_id=PROJECT,
            analysis_run_id=run_id,
            b_model_result_id=result.id,
            source_node_id=source.id,
            source_node_version=source.version,
            target_node_id=target.id if target else None,
            target_node_version=target.version if target else None,
            recommendation=recommendation,
            relation_type=relation_type,
            suggested_title=result.suggested_title,
            suggested_content=result.suggested_content,
            reason=result.reason,
            status="PENDING",
        )
        session.add(candidate)
        session.commit()
        return candidate.id


def _post(client, source_id, payload, *, headers=HEADERS):
    return client.post(
        f"/api/v1/nodes/{source_id}/decisions",
        headers=headers,
        json=payload,
    )


def test_manual_decision_openapi_exposes_the_discriminated_request(client) -> None:
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/api/v1/nodes/{node_id}/decisions"]["post"]
    request_ref = operation["requestBody"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    request_schema = schema["components"]["schemas"][request_ref.rsplit("/", 1)[-1]]
    assert {"requestedAction", "sourceExpectedVersion"} <= set(
        request_schema["required"]
    )
    assert request_schema["properties"]["requestedAction"]["enum"] == [
        "CREATE_NEW",
        "LINK",
        "MERGE",
    ]


def test_b_merge_recommendation_can_be_overridden_with_link(
    client,
    session_factory,
) -> None:
    source_id, version = _node(
        session_factory, meeting_id="manual-override-merge"
    )
    target_id, target_version = _node(
        session_factory, graph_state="ACTIVE"
    )
    run_id = _run(session_factory, source_id, outcome="SKIPPED")
    candidate_id = _recommendation(
        session_factory,
        source_id=source_id,
        run_id=run_id,
        recommendation="MERGE",
        target_id=target_id,
    )

    response = _post(
        client,
        source_id,
        {
            "requestedAction": "LINK",
            "sourceExpectedVersion": version,
            "targetNodeId": str(target_id),
            "targetExpectedVersion": target_version,
            "relationType": "RELATED_TO",
            "analysisRunId": str(run_id),
            "recommendationId": str(candidate_id),
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["requestedAction"] == "LINK"
    assert body["relationId"] is not None
    with session_factory() as session:
        source = session.get(Node, source_id)
        candidate = session.get(AnalysisCandidate, candidate_id)
        event = session.get(
            GraphChangeEvent, uuid.UUID(body["graphChangeEventId"])
        )
        assert source.graph_state == "ACTIVE"
        assert source.version == version + 1
        assert candidate.status == "REJECTED"
        assert event.detail["recommendedAction"] == "MERGE"
        assert event.detail["requestedAction"] == "LINK"
        assert session.scalar(select(func.count()).select_from(Relation)) == 1

    final_review = client.get(
        "/api/v1/meetings/manual-override-merge/final-review",
        headers=HEADERS,
    )
    assert final_review.status_code == 200
    assert final_review.json()["total"] == 0


def test_rejected_link_recommendation_can_be_overridden_with_create(
    client,
    session_factory,
) -> None:
    source_id, version = _node(session_factory)
    target_id, _ = _node(session_factory, graph_state="ACTIVE")
    run_id = _run(session_factory, source_id, outcome="SKIPPED")
    candidate_id = _recommendation(
        session_factory,
        source_id=source_id,
        run_id=run_id,
        recommendation="LINK",
        target_id=target_id,
        relation_type="RELATED_TO",
    )
    rejected = client.post(
        f"/api/v1/analysis-candidates/{candidate_id}/reject",
        headers=HEADERS,
        json={"expectedVersion": 1},
    )
    assert rejected.status_code == 200

    response = _post(
        client,
        source_id,
        {
            "requestedAction": "CREATE_NEW",
            "sourceExpectedVersion": version,
            "analysisRunId": str(run_id),
            "recommendationId": str(candidate_id),
        },
    )

    assert response.status_code == 200, response.text
    with session_factory() as session:
        source = session.get(Node, source_id)
        assert source.graph_state == "ACTIVE"
        assert source.version == version + 1
        assert session.scalar(select(func.count()).select_from(Relation)) == 0


@pytest.mark.parametrize("run_outcome", [None, "SKIPPED", "FAILED"])
def test_manual_create_works_without_candidate_for_every_fallback_state(
    client,
    session_factory,
    run_outcome,
) -> None:
    source_id, version = _node(session_factory)
    run_id = (
        _run(session_factory, source_id, outcome=run_outcome)
        if run_outcome
        else None
    )
    payload = {
        "requestedAction": "CREATE_NEW",
        "sourceExpectedVersion": version,
    }
    if run_id:
        payload["analysisRunId"] = str(run_id)

    response = _post(client, source_id, payload)

    assert response.status_code == 200, response.text
    with session_factory() as session:
        source = session.get(Node, source_id)
        assert source.graph_state == "ACTIVE"
        if run_id:
            run = session.get(NodeAnalysisRun, run_id)
            assert run.status == (
                "COMPLETED" if run_outcome == "SKIPPED" else "FAILED"
            )


def test_manual_decision_supersedes_unfinished_current_run_without_reference(
    client,
    session_factory,
) -> None:
    source_id, version = _node(session_factory)
    run_id = _run(session_factory, source_id, outcome="PENDING")
    with session_factory() as session:
        source = session.get(Node, source_id)
        session.add(
            AnalysisJob(
                project_id=PROJECT,
                external_meeting_id=source.source_meeting_id,
                node_id=source_id,
                node_version=version,
                status="RUNNING",
                attempt_count=1,
                max_attempts=3,
                claim_token=uuid.uuid4(),
                claimed_at=datetime.now(timezone.utc),
                available_at=datetime.now(timezone.utc),
                analysis_run_id=run_id,
            )
        )
        session.commit()

    response = _post(
        client,
        source_id,
        {
            "requestedAction": "CREATE_NEW",
            "sourceExpectedVersion": version,
        },
    )

    assert response.status_code == 200
    with session_factory() as session:
        assert session.get(NodeAnalysisRun, run_id).status == "SUPERSEDED"
        job = session.scalar(
            select(AnalysisJob).where(AnalysisJob.node_id == source_id)
        )
        assert job.status == "FAILED"
        assert job.claim_token is None
        assert job.failure_code == "MANUAL_DECISION_COMPLETED"


def test_manual_create_is_idempotent_without_duplicate_audit_or_outbox(
    client,
    session_factory,
) -> None:
    source_id, version = _node(session_factory)
    payload = {
        "requestedAction": "CREATE_NEW",
        "sourceExpectedVersion": version,
    }

    first = _post(client, source_id, payload)
    replay = _post(client, source_id, payload)

    assert first.status_code == replay.status_code == 200
    assert first.json()["replayed"] is False
    assert replay.json()["replayed"] is True
    assert first.json()["graphChangeEventId"] == replay.json()["graphChangeEventId"]
    with session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(GraphChangeEvent))
            == 1
        )
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


def test_manual_link_replay_does_not_duplicate_relation_or_outbox(
    client,
    session_factory,
) -> None:
    source_id, version = _node(session_factory)
    target_id, target_version = _node(
        session_factory, graph_state="ACTIVE"
    )
    payload = {
        "requestedAction": "LINK",
        "sourceExpectedVersion": version,
        "targetNodeId": str(target_id),
        "targetExpectedVersion": target_version,
        "relationType": "RELATED_TO",
    }

    first = _post(client, source_id, payload)
    replay = _post(client, source_id, payload)

    assert first.status_code == replay.status_code == 200
    assert first.json()["relationId"] == replay.json()["relationId"]
    assert replay.json()["replayed"] is True
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Relation)) == 1
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"requestedAction": "LINK", "sourceExpectedVersion": 1},
        {
            "requestedAction": "LINK",
            "sourceExpectedVersion": 1,
            "targetNodeId": str(uuid.uuid4()),
            "targetExpectedVersion": 1,
        },
        {
            "requestedAction": "MERGE",
            "sourceExpectedVersion": 1,
            "targetNodeId": str(uuid.uuid4()),
            "targetExpectedVersion": 1,
        },
    ],
)
def test_manual_decision_requires_action_specific_fields(client, payload) -> None:
    response = _post(client, uuid.uuid4(), payload)
    assert response.status_code == 422


def test_manual_decision_rejects_source_and_target_version_conflicts(
    client,
    session_factory,
) -> None:
    source_id, version = _node(session_factory)
    target_id, target_version = _node(
        session_factory, graph_state="ACTIVE"
    )
    source_conflict = _post(
        client,
        source_id,
        {
            "requestedAction": "CREATE_NEW",
            "sourceExpectedVersion": version + 1,
        },
    )
    assert source_conflict.status_code == 409
    assert source_conflict.json()["error"]["actualVersion"] == version

    target_conflict = _post(
        client,
        source_id,
        {
            "requestedAction": "LINK",
            "sourceExpectedVersion": version,
            "targetNodeId": str(target_id),
            "targetExpectedVersion": target_version + 1,
            "relationType": "RELATED_TO",
        },
    )
    assert target_conflict.status_code == 409
    assert target_conflict.json()["error"]["actualVersion"] == target_version


def test_manual_decision_hides_cross_project_target_and_rejects_active_source(
    client,
    session_factory,
) -> None:
    source_id, version = _node(session_factory)
    foreign_target, foreign_version = _node(
        session_factory,
        project_id="another-project",
        graph_state="ACTIVE",
    )
    cross_project = _post(
        client,
        source_id,
        {
            "requestedAction": "LINK",
            "sourceExpectedVersion": version,
            "targetNodeId": str(foreign_target),
            "targetExpectedVersion": foreign_version,
            "relationType": "RELATED_TO",
        },
    )
    assert cross_project.status_code == 404

    active_source, active_version = _node(
        session_factory, graph_state="ACTIVE"
    )
    invalid_state = _post(
        client,
        active_source,
        {
            "requestedAction": "CREATE_NEW",
            "sourceExpectedVersion": active_version,
        },
    )
    assert invalid_state.status_code == 409


def test_manual_merge_without_analysis_is_atomic_and_idempotent(
    client,
    session_factory,
) -> None:
    source_id, source_version = _node(session_factory)
    target_id, target_version = _node(
        session_factory, graph_state="ACTIVE"
    )
    payload = {
        "requestedAction": "MERGE",
        "sourceExpectedVersion": source_version,
        "targetNodeId": str(target_id),
        "targetExpectedVersion": target_version,
        "mergedTitle": "사용자가 확정한 병합 제목",
        "mergedContent": "사용자가 확정한 병합 본문",
    }

    first = _post(client, source_id, payload)
    replay = _post(client, source_id, payload)

    assert first.status_code == replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert first.json()["mergeHistoryId"] == replay.json()["mergeHistoryId"]
    with session_factory() as session:
        source = session.get(Node, source_id)
        target = session.get(Node, target_id)
        history = session.execute(select(NodeMergeHistory)).scalar_one()
        assert source.graph_state == "MERGED"
        assert source.merged_into_node_id == target.id
        assert target.graph_state == "ACTIVE"
        assert target.title == payload["mergedTitle"]
        assert history.analysis_run_id is None
        assert history.candidate_id is None
        assert (
            session.scalar(select(func.count()).select_from(NodeMergeHistory))
            == 1
        )
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
