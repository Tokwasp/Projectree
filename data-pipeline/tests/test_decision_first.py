"""Decision-first scheduling from FastAPI through the durable PostgreSQL jobs."""

from __future__ import annotations

import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from data_pipeline.retrieval.embedding import EMBEDDING_CONTRACT_VERSION
from data_pipeline.analysis_worker import AnalysisWorker
from data_pipeline.api.app import create_app
from data_pipeline.api.dependencies import get_session_factory
from data_pipeline.llm import LLMResponse
from data_pipeline.pipeline import run_meeting
from data_pipeline.pipeline.parent_hint import resolve_same_meeting_parent_hint
from data_pipeline.storage import (
    AnalysisCandidate,
    AnalysisJob,
    BModelResult,
    Meeting,
    Node,
    NodeAnalysisRun,
    OutboxEvent,
)

from .support import ev, item, judgment, seg

PROJECT = "proj-decision-first"
HEADERS = {
    "X-Project-Id": PROJECT,
    "X-Actor-Id": "decision-first-reviewer",
}


class _ScriptedClient:
    class _Settings:
        model = "fake-model"
        temperature = 0.0

    settings = _Settings()

    def __init__(self, responses: list[dict]):
        self._responses = [
            json.dumps(response, ensure_ascii=False) for response in responses
        ]
        self.calls = 0

    def complete(self, messages):
        del messages
        response = LLMResponse(
            raw_response=self._responses[self.calls],
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            latency_ms=1,
        )
        self.calls += 1
        return response


class _Embedding:
    def embed(self, *, text: str, model: str, dimensions: int):
        del text, model
        return [1.0, *([0.0] * (dimensions - 1))]


class _AttachActionBModel:
    def recommend(self, *, source_node, retrieval_candidates, model):
        del model
        assert source_node["nodeType"] == "ACTION"
        decision = next(
            row
            for row in retrieval_candidates
            if row["nodeType"] == "DECISION"
        )
        return {
            "recommendation": "LINK",
            "targetNodeId": decision["nodeId"],
            "relationType": "ATTACHED_TO",
            "suggestedTitle": source_node["title"],
            "suggestedContent": source_node["content"],
            "reason": "the confirmed Decision is the structural parent",
        }


@pytest.fixture()
def client(session_factory):
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _run_graph(
    session_factory,
    *,
    meeting_id: str,
    project_id: str = PROJECT,
    decision_count: int = 1,
    action_count: int = 1,
    issue_count: int = 0,
    attach_to_first_decision: bool = False,
) -> None:
    extraction_items: list[dict] = []
    judgments: list[dict] = []
    segments: list[dict] = []

    for index in range(decision_count):
        item_id = f"d{index + 1}"
        quote = f"Decision evidence sentence number {index + 1}"
        extraction_items.append(
            item(
                item_id,
                "DECISION",
                f"Decision title {index + 1}",
                f"Decision content {index + 1}",
                [ev(f"s-{item_id}", quote)],
            )
        )
        judgments.append(
            judgment(item_id, "NEW_DECISION", category="BACKEND")
        )
        segments.append(seg(f"s-{item_id}", quote))

    for index in range(action_count):
        item_id = f"a{index + 1}"
        quote = f"Action evidence sentence number {index + 1}"
        action = item(
            item_id,
            "ACTION",
            f"Action title {index + 1}",
            f"Action content {index + 1}",
            [ev(f"s-{item_id}", quote)],
        )
        extraction_items.append(action)
        if attach_to_first_decision:
            judgments.append(
                judgment(item_id, "ATTACH", attachTo="d1")
            )
        else:
            judgments.append(
                judgment(
                    item_id,
                    "MINUTES_ONLY",
                    reason="NO_RELATED_DECISION",
                )
            )
        segments.append(seg(f"s-{item_id}", quote))

    for index in range(issue_count):
        item_id = f"i{index + 1}"
        quote = f"Issue evidence sentence number {index + 1}"
        issue = item(
            item_id,
            "ISSUE",
            f"Issue title {index + 1}",
            f"Issue content {index + 1}",
            [ev(f"s-{item_id}", quote)],
        )
        extraction_items.append(issue)
        judgments.append(
            judgment(
                item_id,
                "MINUTES_ONLY",
                reason="NO_RELATED_DECISION",
            )
        )
        segments.append(seg(f"s-{item_id}", quote))

    profile = "candidate-quality-v1" if attach_to_first_decision else None
    run_meeting(
        session_factory,
        meeting_input={
            "requestId": f"request-{meeting_id}",
            "projectId": project_id,
            "externalMeetingId": meeting_id,
            "segments": segments,
        },
        client=_ScriptedClient(
            [
                {"meetingId": meeting_id, "items": extraction_items},
                {"meetingId": meeting_id, "judgments": judgments},
            ]
        ),
        **({"prompt_profile": profile} if profile else {}),
    )


def _complete_initial_review(
    client: TestClient,
    meeting_id: str,
    *,
    headers: dict[str, str] = HEADERS,
):
    response = client.post(
        f"/api/v1/meetings/{meeting_id}/initial-review/complete",
        headers=headers,
        json={},
    )
    assert response.status_code == 202, response.text
    return response


def _nodes(session_factory, meeting_id: str, *, project_id: str = PROJECT):
    with session_factory() as session:
        rows = session.execute(
            select(Node).where(
                Node.project_id == project_id,
                Node.source_meeting_id == meeting_id,
            )
        ).scalars().all()
        return {row.source_item_id: (row.id, row.version) for row in rows}


def _post_manual(
    client: TestClient,
    source_id: uuid.UUID,
    version: int,
    *,
    action: str = "CREATE_NEW",
    target: tuple[uuid.UUID, int] | None = None,
    analysis_run_id: uuid.UUID | None = None,
    headers: dict[str, str] = HEADERS,
):
    payload: dict = {
        "requestedAction": action,
        "sourceExpectedVersion": version,
    }
    if analysis_run_id is not None:
        payload["analysisRunId"] = str(analysis_run_id)
    if target is not None:
        payload.update(
            {
                "targetNodeId": str(target[0]),
                "targetExpectedVersion": target[1],
            }
        )
    if action == "LINK":
        payload["relationType"] = "RELATED_TO"
    elif action == "MERGE":
        payload["mergedTitle"] = "Merged Decision title"
        payload["mergedContent"] = "Merged Decision content"
    return client.post(
        f"/api/v1/nodes/{source_id}/decisions",
        headers=headers,
        json=payload,
    )


def _active_decision(
    session_factory,
    *,
    project_id: str = PROJECT,
    meeting_id: str = "older-meeting",
) -> tuple[uuid.UUID, int]:
    with session_factory() as session:
        node = Node(
            project_id=project_id,
            source_meeting_id=meeting_id,
            source_item_id=f"target-{uuid.uuid4()}",
            node_type="DECISION",
            category="BACKEND",
            title="Existing Decision",
            content="Existing Decision content",
            graph_state="ACTIVE",
            analysis_status="ANALYZED",
        )
        session.add(node)
        session.commit()
        return node.id, node.version


def _jobs_by_type(session_factory, meeting_id: str):
    with session_factory() as session:
        return session.execute(
            select(Node.node_type, AnalysisJob.status)
            .join(AnalysisJob, AnalysisJob.node_id == Node.id)
            .where(
                Node.project_id == PROJECT,
                Node.source_meeting_id == meeting_id,
            )
            .order_by(Node.node_type, Node.source_item_id)
        ).all()


def _analysis_queued_count(session_factory, meeting_id: str) -> int:
    with session_factory() as session:
        return session.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(
                OutboxEvent.project_id == PROJECT,
                OutboxEvent.event_type == "ANALYSIS_QUEUED",
                OutboxEvent.payload["meetingId"].as_string() == meeting_id,
            )
        )


def _analysis_side_effects(
    session_factory,
    node_id: uuid.UUID,
) -> dict[str, object]:
    with session_factory() as session:
        node = session.get(Node, node_id)
        return {
            "runs": session.scalar(
                select(func.count())
                .select_from(NodeAnalysisRun)
                .where(NodeAnalysisRun.source_node_id == node_id)
            ),
            "jobs": session.scalar(
                select(func.count())
                .select_from(AnalysisJob)
                .where(AnalysisJob.node_id == node_id)
            ),
            "outbox": session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.aggregate_type == "node",
                    OutboxEvent.aggregate_id == str(node_id),
                    OutboxEvent.event_type == "ANALYSIS_QUEUED",
                )
            ),
            "candidates": session.scalar(
                select(func.count())
                .select_from(AnalysisCandidate)
                .where(AnalysisCandidate.source_node_id == node_id)
            ),
            "analysis_status": node.analysis_status,
            "current_run_id": node.current_analysis_run_id,
            "version": node.version,
        }


def _reanalyze(
    client: TestClient,
    node: tuple[uuid.UUID, int],
    *,
    headers: dict[str, str] = HEADERS,
):
    return client.post(
        f"/api/v1/nodes/{node[0]}/reanalyze",
        headers=headers,
        json={"expectedVersion": node[1]},
    )


def _attach_terminal_run(
    session_factory,
    source_id: uuid.UUID,
    *,
    outcome: str,
) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        source = session.get(Node, source_id)
        run = NodeAnalysisRun(
            source_node_id=source.id,
            source_node_version=source.version,
            analysis_input_hash=uuid.uuid4().hex * 2,
            analysis_input_hash_version="analysis-input-v2",
            retrieval_config_version="retrieval-test-v1",
            embedding_model="text-embedding-3-small",
            embedding_version=EMBEDDING_CONTRACT_VERSION,
            retrieval_status="COMPLETED",
            retrieval_result_count=0,
            retrieval_completed_at=now,
            b_model_status="SKIPPED" if outcome == "SKIPPED" else "FAILED",
            b_model_skip_reason=(
                "NO_RETRIEVAL_CANDIDATES"
                if outcome == "SKIPPED"
                else None
            ),
            b_model_failure_code=(
                "B_MODEL_FAILED" if outcome == "FAILED" else None
            ),
            b_model_completed_at=now,
            attempt=1,
            status="COMPLETED" if outcome == "SKIPPED" else "FAILED",
            requested_by="test",
            failure_code=(
                "B_MODEL_FAILED" if outcome == "FAILED" else None
            ),
            completed_at=now,
        )
        session.add(run)
        session.flush()
        source.current_analysis_run_id = run.id
        source.analysis_input_hash = run.analysis_input_hash
        source.analysis_status = (
            "ANALYZED" if outcome == "SKIPPED" else "FAILED"
        )
        job = session.scalar(
            select(AnalysisJob).where(AnalysisJob.node_id == source.id)
        )
        job.status = "SUCCEEDED" if outcome == "SKIPPED" else "FAILED"
        job.analysis_run_id = run.id
        job.failure_code = (
            None if outcome == "SKIPPED" else "B_MODEL_FAILED"
        )
        session.commit()
        return run.id


def _create_create_new_recommendation(
    session_factory,
    source_id: uuid.UUID,
) -> uuid.UUID:
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        source = session.get(Node, source_id)
        run = NodeAnalysisRun(
            source_node_id=source.id,
            source_node_version=source.version,
            analysis_input_hash=uuid.uuid4().hex * 2,
            analysis_input_hash_version="analysis-input-v2",
            retrieval_config_version="retrieval-test-v1",
            embedding_model="text-embedding-3-small",
            embedding_version=EMBEDDING_CONTRACT_VERSION,
            retrieval_status="COMPLETED",
            retrieval_result_count=0,
            retrieval_completed_at=now,
            b_model_status="SUCCEEDED",
            b_model_completed_at=now,
            attempt=1,
            status="COMPLETED",
            requested_by="test",
            completed_at=now,
        )
        session.add(run)
        session.flush()
        source.current_analysis_run_id = run.id
        source.analysis_input_hash = run.analysis_input_hash
        source.analysis_status = "ANALYZED"
        job = session.scalar(
            select(AnalysisJob).where(AnalysisJob.node_id == source.id)
        )
        job.status = "SUCCEEDED"
        job.analysis_run_id = run.id
        result = BModelResult(
            project_id=PROJECT,
            analysis_run_id=run.id,
            source_node_id=source.id,
            source_node_version=source.version,
            recommendation="CREATE_NEW",
            suggested_title=source.title,
            suggested_content=source.content,
            reason="fake recommendation",
            model="fake-b",
            model_version="v1",
            metadata_json={},
            validation_status="VALIDATED",
        )
        session.add(result)
        session.flush()
        candidate = AnalysisCandidate(
            project_id=PROJECT,
            analysis_run_id=run.id,
            b_model_result_id=result.id,
            source_node_id=source.id,
            source_node_version=source.version,
            recommendation="CREATE_NEW",
            suggested_title=source.title,
            suggested_content=source.content,
            reason=result.reason,
            status="PENDING",
        )
        session.add(candidate)
        session.commit()
        return candidate.id


def test_initial_review_queues_only_decisions(client, session_factory) -> None:
    meeting_id = "decision-first-initial"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=1,
        action_count=1,
        issue_count=1,
    )

    response = _complete_initial_review(client, meeting_id)

    assert response.json()["queuedAnalysisJobCount"] == 1
    assert _jobs_by_type(session_factory, meeting_id) == [
        ("DECISION", "PENDING")
    ]


def test_no_decision_meeting_immediately_queues_dependents(
    client,
    session_factory,
) -> None:
    meeting_id = "decision-first-no-decision"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=0,
        action_count=1,
        issue_count=1,
    )

    response = _complete_initial_review(client, meeting_id)

    assert response.json()["queuedAnalysisJobCount"] == 2
    assert _jobs_by_type(session_factory, meeting_id) == [
        ("ACTION", "PENDING"),
        ("ISSUE", "PENDING"),
    ]


def test_manual_job_completion_reason_is_not_reported_as_pipeline_failure(
    client,
    session_factory,
) -> None:
    meeting_id = "decision-first-manual-terminal"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=1,
        action_count=0,
    )
    _complete_initial_review(client, meeting_id)
    decision = _nodes(session_factory, meeting_id)["d1"]

    response = _post_manual(client, *decision)

    assert response.status_code == 200, response.text
    pipeline = client.get(
        f"/api/v1/meetings/{meeting_id}/pipeline-status",
        headers=HEADERS,
    ).json()
    analysis = client.get(
        f"/api/v1/meetings/{meeting_id}/analysis-status",
        headers=HEADERS,
    ).json()
    assert pipeline["pipelineStage"] == "REVIEW_COMPLETED"
    assert analysis["status"] == "REVIEW_COMPLETED"
    assert analysis["jobs"][0]["status"] == "FAILED"
    assert (
        analysis["jobs"][0]["failureCode"]
        == "MANUAL_DECISION_COMPLETED"
    )


def test_dependents_wait_until_every_decision_is_final(
    client,
    session_factory,
) -> None:
    meeting_id = "decision-first-two-decisions"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=2,
        action_count=1,
    )
    _complete_initial_review(client, meeting_id)
    nodes = _nodes(session_factory, meeting_id)

    first = _post_manual(client, *nodes["d1"])
    assert first.status_code == 200, first.text
    assert _jobs_by_type(session_factory, meeting_id) == [
        ("DECISION", "FAILED"),
        ("DECISION", "PENDING"),
    ]

    last = _post_manual(client, *nodes["d2"])
    assert last.status_code == 200, last.text
    assert _jobs_by_type(session_factory, meeting_id) == [
        ("ACTION", "PENDING"),
        ("DECISION", "FAILED"),
        ("DECISION", "FAILED"),
    ]


@pytest.mark.parametrize("decision_action", ["CREATE_NEW", "LINK", "MERGE"])
def test_every_decision_outcome_releases_dependents(
    client,
    session_factory,
    decision_action: str,
) -> None:
    meeting_id = f"decision-first-{decision_action.lower()}"
    _run_graph(session_factory, meeting_id=meeting_id)
    _complete_initial_review(client, meeting_id)
    decision = _nodes(session_factory, meeting_id)["d1"]
    target = (
        _active_decision(session_factory)
        if decision_action in {"LINK", "MERGE"}
        else None
    )

    response = _post_manual(
        client,
        *decision,
        action=decision_action,
        target=target,
    )

    assert response.status_code == 200, response.text
    assert ("ACTION", "PENDING") in _jobs_by_type(
        session_factory, meeting_id
    )


@pytest.mark.parametrize("run_outcome", ["SKIPPED", "FAILED"])
def test_terminal_b_model_fallback_still_releases_dependents(
    client,
    session_factory,
    run_outcome: str,
) -> None:
    meeting_id = f"decision-first-{run_outcome.lower()}"
    _run_graph(session_factory, meeting_id=meeting_id)
    _complete_initial_review(client, meeting_id)
    decision_id, version = _nodes(session_factory, meeting_id)["d1"]
    run_id = _attach_terminal_run(
        session_factory,
        decision_id,
        outcome=run_outcome,
    )

    response = _post_manual(
        client,
        decision_id,
        version,
        analysis_run_id=run_id,
    )

    assert response.status_code == 200, response.text
    assert ("ACTION", "PENDING") in _jobs_by_type(
        session_factory, meeting_id
    )


def test_existing_recommendation_approval_releases_dependents(
    client,
    session_factory,
) -> None:
    meeting_id = "decision-first-existing-approval"
    _run_graph(session_factory, meeting_id=meeting_id)
    _complete_initial_review(client, meeting_id)
    source_id, _ = _nodes(session_factory, meeting_id)["d1"]
    candidate_id = _create_create_new_recommendation(
        session_factory,
        source_id,
    )

    response = client.post(
        f"/api/v1/analysis-candidates/{candidate_id}/approve-create",
        headers=HEADERS,
        json={"expectedVersion": 1},
    )

    assert response.status_code == 200, response.text
    assert ("ACTION", "PENDING") in _jobs_by_type(
        session_factory, meeting_id
    )


def test_phase_release_repairs_only_missing_jobs(
    client,
    session_factory,
) -> None:
    meeting_id = "decision-first-partial-repair"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=1,
        action_count=2,
    )
    _complete_initial_review(client, meeting_id)
    nodes = _nodes(session_factory, meeting_id)
    with session_factory() as session:
        first_action = session.get(Node, nodes["a1"][0])
        session.add(
            AnalysisJob(
                project_id=PROJECT,
                external_meeting_id=meeting_id,
                node_id=first_action.id,
                node_version=first_action.version,
                status="PENDING",
                attempt_count=0,
                max_attempts=3,
                available_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

    response = _post_manual(client, *nodes["d1"])

    assert response.status_code == 200, response.text
    with session_factory() as session:
        action_jobs = session.scalar(
            select(func.count())
            .select_from(AnalysisJob)
            .join(Node, Node.id == AnalysisJob.node_id)
            .where(
                Node.source_meeting_id == meeting_id,
                Node.node_type == "ACTION",
            )
        )
    assert action_jobs == 2
    assert _analysis_queued_count(session_factory, meeting_id) == 2


def test_merge_parent_hint_uses_final_canonical_decision(
    client,
    session_factory,
) -> None:
    meeting_id = "decision-first-canonical"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        attach_to_first_decision=True,
    )
    _complete_initial_review(client, meeting_id)
    nodes = _nodes(session_factory, meeting_id)
    first_target = _active_decision(
        session_factory,
        meeting_id="canonical-level-one",
    )
    final_target = _active_decision(
        session_factory,
        meeting_id="canonical-level-two",
    )

    response = _post_manual(
        client,
        *nodes["d1"],
        action="MERGE",
        target=first_target,
    )
    assert response.status_code == 200, response.text

    with session_factory() as session:
        level_one = session.get(Node, first_target[0])
        level_one.graph_state = "MERGED"
        level_one.merged_into_node_id = final_target[0]
        level_one.version += 1
        session.commit()
        action = session.get(Node, nodes["a1"][0])
        hint = resolve_same_meeting_parent_hint(session, action)
    assert hint is not None
    assert hint.node_id == final_target[0]

    # Corrupted merge cycles are rejected rather than followed indefinitely.
    with session_factory() as session:
        level_two = session.get(Node, final_target[0])
        level_two.graph_state = "MERGED"
        level_two.merged_into_node_id = first_target[0]
        session.commit()
        action = session.get(Node, nodes["a1"][0])
        assert resolve_same_meeting_parent_hint(session, action) is None


def test_phase_release_is_isolated_by_project_and_meeting(
    client,
    session_factory,
) -> None:
    first_meeting = "decision-first-isolated-a"
    second_meeting = "decision-first-isolated-b"
    _run_graph(session_factory, meeting_id=first_meeting)
    _run_graph(session_factory, meeting_id=second_meeting)
    _complete_initial_review(client, first_meeting)
    _complete_initial_review(client, second_meeting)
    first_decision = _nodes(session_factory, first_meeting)["d1"]

    response = _post_manual(client, *first_decision)

    assert response.status_code == 200, response.text
    assert ("ACTION", "PENDING") in _jobs_by_type(
        session_factory, first_meeting
    )
    assert ("ACTION", "PENDING") not in _jobs_by_type(
        session_factory, second_meeting
    )


def test_concurrent_last_decisions_release_each_dependent_once(
    session_factory,
) -> None:
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL row locks")

    meeting_id = "decision-first-concurrent"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=2,
        action_count=1,
        issue_count=1,
    )
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as initial_client:
        _complete_initial_review(initial_client, meeting_id)
    nodes = _nodes(session_factory, meeting_id)
    barrier = Barrier(2)

    def approve(item_id: str):
        local_app = create_app()
        local_app.dependency_overrides[get_session_factory] = (
            lambda: session_factory
        )
        with TestClient(local_app) as local_client:
            barrier.wait(timeout=10)
            return _post_manual(local_client, *nodes[item_id])

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(approve, ("d1", "d2")))

    assert [response.status_code for response in responses] == [200, 200]
    with session_factory() as session:
        dependent_jobs = session.scalar(
            select(func.count())
            .select_from(AnalysisJob)
            .join(Node, Node.id == AnalysisJob.node_id)
            .where(
                Node.source_meeting_id == meeting_id,
                Node.node_type.in_(("ACTION", "ISSUE")),
            )
        )
    assert dependent_jobs == 2
    assert _analysis_queued_count(session_factory, meeting_id) == 4


def test_fake_worker_e2e_completes_without_parent_rule_409(
    client,
    session_factory,
) -> None:
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("pgvector Retrieval E2E requires PostgreSQL")

    meeting_id = "decision-first-worker-e2e"
    _run_graph(session_factory, meeting_id=meeting_id)
    _complete_initial_review(client, meeting_id)
    nodes = _nodes(session_factory, meeting_id)
    worker = AnalysisWorker(
        session_factory=session_factory,
        embedding_client=_Embedding(),
        b_model_client=_AttachActionBModel(),
        b_model_name="fake-b",
        b_model_version="v1",
    )

    decision_analysis = worker.run_once()
    assert decision_analysis.succeeded == 1
    manual = _post_manual(client, *nodes["d1"])
    assert manual.status_code == 200, manual.text

    action_analysis = worker.run_once()
    assert action_analysis.succeeded == 1
    with session_factory() as session:
        candidate = session.scalar(
            select(AnalysisCandidate)
            .join(Node, Node.id == AnalysisCandidate.source_node_id)
            .where(
                Node.source_meeting_id == meeting_id,
                Node.node_type == "ACTION",
                AnalysisCandidate.status == "PENDING",
            )
        )

    approved = client.post(
        f"/api/v1/analysis-candidates/{candidate.id}/approve-link",
        headers=HEADERS,
        json={"expectedVersion": candidate.version},
    )

    assert approved.status_code == 200, approved.text
    with session_factory() as session:
        action = session.get(Node, nodes["a1"][0])
        assert action.graph_state == "ACTIVE"
        assert action.parent_id == nodes["d1"][0]
        assert session.scalar(
            select(func.count())
            .select_from(Node)
            .where(
                Node.source_meeting_id == meeting_id,
                Node.graph_state == "UNATTACHED",
            )
        ) == 0


@pytest.mark.parametrize(
    ("item_id", "action_count", "issue_count"),
    [("a1", 1, 0), ("i1", 0, 1)],
)
def test_dependent_reanalysis_is_blocked_without_side_effects(
    client,
    session_factory,
    item_id: str,
    action_count: int,
    issue_count: int,
) -> None:
    meeting_id = f"reanalyze-blocked-{item_id}"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=1,
        action_count=action_count,
        issue_count=issue_count,
    )
    _complete_initial_review(client, meeting_id)
    node = _nodes(session_factory, meeting_id)[item_id]
    before = _analysis_side_effects(session_factory, node[0])

    response = _reanalyze(client, node)

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "DEPENDENT_ANALYSIS_BLOCKED"
    assert "every Decision" in response.json()["error"]["message"]
    assert _analysis_side_effects(session_factory, node[0]) == before


@pytest.mark.parametrize("decision_result", ["COMPLETED", "SKIPPED", "FAILED"])
def test_dependent_reanalysis_waits_for_user_final_decision(
    client,
    session_factory,
    decision_result: str,
) -> None:
    meeting_id = f"reanalyze-model-terminal-{decision_result.lower()}"
    _run_graph(session_factory, meeting_id=meeting_id)
    _complete_initial_review(client, meeting_id)
    nodes = _nodes(session_factory, meeting_id)
    if decision_result == "COMPLETED":
        _create_create_new_recommendation(session_factory, nodes["d1"][0])
    else:
        _attach_terminal_run(
            session_factory,
            nodes["d1"][0],
            outcome=decision_result,
        )
    before = _analysis_side_effects(session_factory, nodes["a1"][0])

    response = _reanalyze(client, nodes["a1"])

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "DEPENDENT_ANALYSIS_BLOCKED"
    assert _analysis_side_effects(session_factory, nodes["a1"][0]) == before


def test_decision_reanalysis_remains_allowed(
    client,
    session_factory,
) -> None:
    meeting_id = "reanalyze-decision-allowed"
    _run_graph(session_factory, meeting_id=meeting_id)
    _complete_initial_review(client, meeting_id)
    decision = _nodes(session_factory, meeting_id)["d1"]
    before = _analysis_side_effects(session_factory, decision[0])

    response = _reanalyze(client, decision)

    assert response.status_code == 202, response.text
    after = _analysis_side_effects(session_factory, decision[0])
    assert after["runs"] == before["runs"] + 1
    assert after["jobs"] == before["jobs"]
    assert after["outbox"] == before["outbox"]
    assert after["analysis_status"] == "PENDING"


@pytest.mark.parametrize("decision_action", ["CREATE_NEW", "MERGE"])
def test_dependent_reanalysis_is_allowed_after_final_decision(
    client,
    session_factory,
    decision_action: str,
) -> None:
    meeting_id = f"reanalyze-after-{decision_action.lower()}"
    _run_graph(session_factory, meeting_id=meeting_id)
    _complete_initial_review(client, meeting_id)
    nodes = _nodes(session_factory, meeting_id)
    target = (
        _active_decision(session_factory)
        if decision_action == "MERGE"
        else None
    )
    decided = _post_manual(
        client,
        *nodes["d1"],
        action=decision_action,
        target=target,
    )
    assert decided.status_code == 200, decided.text

    before = _analysis_side_effects(session_factory, nodes["a1"][0])
    response = _reanalyze(client, nodes["a1"])

    assert response.status_code == 202, response.text
    after = _analysis_side_effects(session_factory, nodes["a1"][0])
    assert after["runs"] == before["runs"] + 1
    assert after["jobs"] == before["jobs"]
    assert after["outbox"] == before["outbox"]
    if decision_action == "MERGE":
        with session_factory() as session:
            source = session.get(Node, nodes["d1"][0])
            canonical = session.get(Node, source.merged_into_node_id)
            assert source.graph_state == "MERGED"
            assert canonical.graph_state == "ACTIVE"


def test_dependent_reanalysis_is_allowed_without_decisions(
    client,
    session_factory,
) -> None:
    meeting_id = "reanalyze-no-decisions"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=0,
        action_count=1,
    )
    _complete_initial_review(client, meeting_id)
    action = _nodes(session_factory, meeting_id)["a1"]

    response = _reanalyze(client, action)

    assert response.status_code == 202, response.text
    state = _analysis_side_effects(session_factory, action[0])
    assert state["runs"] == 1
    assert state["jobs"] == 1
    assert state["outbox"] == 1


@pytest.mark.parametrize("isolation", ["MEETING", "PROJECT"])
def test_pending_decision_isolated_from_other_scope(
    client,
    session_factory,
    isolation: str,
) -> None:
    current_meeting = f"reanalyze-isolation-{isolation.lower()}"
    _run_graph(
        session_factory,
        meeting_id=current_meeting,
        decision_count=0,
        action_count=1,
    )
    _complete_initial_review(client, current_meeting)

    if isolation == "MEETING":
        other_meeting = current_meeting + "-other"
        _run_graph(session_factory, meeting_id=other_meeting)
        _complete_initial_review(client, other_meeting)
    else:
        other_project = "proj-reanalyze-other"
        other_headers = {
            "X-Project-Id": other_project,
            "X-Actor-Id": "other-reviewer",
        }
        _run_graph(
            session_factory,
            meeting_id=current_meeting,
            project_id=other_project,
        )
        _complete_initial_review(
            client,
            current_meeting,
            headers=other_headers,
        )

    action = _nodes(session_factory, current_meeting)["a1"]
    response = _reanalyze(client, action)

    assert response.status_code == 202, response.text
    assert _analysis_side_effects(session_factory, action[0])["runs"] == 1


def test_reanalysis_replay_does_not_duplicate_job_or_outbox(
    client,
    session_factory,
) -> None:
    meeting_id = "reanalyze-idempotent"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=0,
        action_count=1,
    )
    _complete_initial_review(client, meeting_id)
    action = _nodes(session_factory, meeting_id)["a1"]
    before = _analysis_side_effects(session_factory, action[0])

    first = _reanalyze(client, action)
    second = _reanalyze(client, action)

    assert first.status_code == second.status_code == 202
    assert first.json()["analysisRunId"] == second.json()["analysisRunId"]
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    after = _analysis_side_effects(session_factory, action[0])
    assert after["runs"] == before["runs"] + 1
    assert after["jobs"] == before["jobs"]
    assert after["outbox"] == before["outbox"]


@pytest.mark.parametrize(
    ("item_id", "action_count", "issue_count"),
    [("a1", 1, 0), ("i1", 0, 1)],
)
def test_last_decision_approval_and_dependent_reanalysis_are_serialized(
    session_factory,
    item_id: str,
    action_count: int,
    issue_count: int,
) -> None:
    with session_factory() as session:
        if session.get_bind().dialect.name != "postgresql":
            pytest.skip("requires PostgreSQL row locks")

    meeting_id = f"reanalyze-concurrent-{item_id}"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=1,
        action_count=action_count,
        issue_count=issue_count,
    )
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as initial_client:
        _complete_initial_review(initial_client, meeting_id)
    nodes = _nodes(session_factory, meeting_id)
    barrier = Barrier(2)

    def approve():
        local_app = create_app()
        local_app.dependency_overrides[get_session_factory] = (
            lambda: session_factory
        )
        with TestClient(local_app) as local_client:
            barrier.wait(timeout=10)
            return _post_manual(local_client, *nodes["d1"])

    def reanalyze():
        local_app = create_app()
        local_app.dependency_overrides[get_session_factory] = (
            lambda: session_factory
        )
        with TestClient(local_app) as local_client:
            barrier.wait(timeout=10)
            return _reanalyze(local_client, nodes[item_id])

    with ThreadPoolExecutor(max_workers=2) as executor:
        approval_future = executor.submit(approve)
        reanalysis_future = executor.submit(reanalyze)
        approval = approval_future.result(timeout=20)
        reanalysis = reanalysis_future.result(timeout=20)

    assert approval.status_code == 200, approval.text
    assert reanalysis.status_code in {202, 409}, reanalysis.text
    if reanalysis.status_code == 409:
        assert (
            reanalysis.json()["error"]["code"]
            == "DEPENDENT_ANALYSIS_BLOCKED"
        )
    state = _analysis_side_effects(session_factory, nodes[item_id][0])
    assert state["runs"] in {0, 1}
    assert state["jobs"] == 1
    assert state["outbox"] == 1
    assert state["candidates"] == 0


def test_automatic_dependent_release_still_emits_exactly_once(
    client,
    session_factory,
) -> None:
    meeting_id = "reanalyze-automatic-release-regression"
    _run_graph(
        session_factory,
        meeting_id=meeting_id,
        decision_count=1,
        action_count=1,
        issue_count=1,
    )
    _complete_initial_review(client, meeting_id)
    nodes = _nodes(session_factory, meeting_id)

    response = _post_manual(client, *nodes["d1"])

    assert response.status_code == 200, response.text
    for item_id in ("a1", "i1"):
        state = _analysis_side_effects(session_factory, nodes[item_id][0])
        assert state["jobs"] == 1
        assert state["outbox"] == 1
        assert state["runs"] == 0
