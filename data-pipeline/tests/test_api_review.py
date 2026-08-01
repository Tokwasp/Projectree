"""FastAPI review API and the Candidate ACTION lifecycle carried through it."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from data_pipeline.api.app import create_app
from data_pipeline.api.dependencies import get_session_factory
from data_pipeline.llm import LLMResponse
from data_pipeline.storage import AnalysisJob, Node, OutboxEvent

from .support import ev, item, judgment, seg

PROJECT = "proj-api"
MEETING = "meet-api"
HEADERS = {"X-Project-Id": PROJECT, "X-Actor-Id": "reviewer-1"}


class _ScriptedClient:
    """Returns canned extraction then judgment JSON, like the other suites."""

    class _S:
        model = "fake-model"
        temperature = 0.0

    settings = _S()

    def __init__(self, responses: list[dict]):
        self._responses = [json.dumps(r, ensure_ascii=False) for r in responses]
        self.calls = 0

    def complete(self, messages):
        del messages
        raw = self._responses[self.calls]
        self.calls += 1
        return LLMResponse(
            raw_response=raw,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            latency_ms=1,
        )


@pytest.fixture()
def client(session_factory):
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _run_meeting(session_factory, *, lifecycle: str | None = None, meeting=MEETING):
    """Persist one ACTION and one DECISION candidate via the real chain."""

    from data_pipeline.pipeline import run_meeting

    action = item(
        "m1",
        "ACTION",
        "CORS 설정을 적용한다",
        "CORS 설정을 적용한다",
        [ev("s1", "그다음에 CORS 설정하고")],
    )
    if lifecycle is not None:
        action["lifecycleStatus"] = lifecycle
    decision = item(
        "m2",
        "DECISION",
        "개인 기능은 EC2 를 쓴다",
        "개인 기능은 EC2 를 쓴다",
        [ev("s2", "개인 기능은 EC2 씁니다")],
    )
    segments = [
        seg("s1", "그다음에 CORS 설정하고"),
        seg("s2", "개인 기능은 EC2 씁니다"),
    ]
    extraction = {"meetingId": meeting, "items": [action, decision]}
    # The frozen PoC LTS judgment contract never emits UNATTACHED; the server
    # derives it from ACTION + MINUTES_ONLY(NO_RELATED_DECISION).
    judgments = {
        "meetingId": meeting,
        "judgments": [
            judgment("m1", "MINUTES_ONLY", reason="NO_RELATED_DECISION"),
            judgment("m2", "NEW_DECISION", category="BACKEND"),
        ],
    }
    run_meeting(
        session_factory,
        meeting_input={
            "requestId": f"req-{meeting}",
            "projectId": PROJECT,
            "externalMeetingId": meeting,
            "segments": segments,
        },
        client=_ScriptedClient([extraction, judgments]),
    )


# ------------------------------------------------------------------ health ---


def test_health_live(client) -> None:
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_ready_checks_config_and_database(client) -> None:
    response = client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["config"] == "ok"
    assert body["checks"]["schema"] == "ok"


def test_request_id_is_echoed_without_logging_request_content(client) -> None:
    response = client.get(
        "/health/live",
        headers={"X-Request-Id": "spring-request-123"},
    )
    assert response.headers["X-Request-Id"] == "spring-request-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_oversized_request_body_is_rejected_before_validation(client) -> None:
    response = client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers={**HEADERS, "Content-Type": "application/json"},
        content=b"x" * 1_048_577,
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "REQUEST_BODY_TOO_LARGE"
    assert response.headers["X-Request-Id"]


def test_chunked_oversized_request_cannot_bypass_the_body_limit() -> None:
    import asyncio

    from data_pipeline.api.middleware import RequestBodyLimitMiddleware

    messages = iter(
        [
            {
                "type": "http.request",
                "body": b"x" * 600_000,
                "more_body": True,
            },
            {
                "type": "http.request",
                "body": b"y" * 600_000,
                "more_body": False,
            },
        ]
    )
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def consuming_app(scope, receive, send):
        del scope, send
        while True:
            message = await receive()
            if not message.get("more_body"):
                return

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [],
    }
    asyncio.run(
        RequestBodyLimitMiddleware(consuming_app)(scope, receive, send)
    )

    response_start = next(
        message for message in sent if message["type"] == "http.response.start"
    )
    assert response_start["status"] == 413


def test_openapi_schema_is_generated(client) -> None:
    spec = client.get("/openapi.json").json()
    assert spec["openapi"].startswith("3.")
    assert "/api/v1/meetings/{meeting_id}/candidates" in spec["paths"]


# -------------------------------------------------------------- candidates ---


def test_list_candidates_for_a_meeting(client, session_factory) -> None:
    _run_meeting(session_factory)

    response = client.get(
        f"/api/v1/meetings/{MEETING}/candidates", headers=HEADERS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meetingId"] == MEETING
    assert body["total"] == 2
    assert {c["suggested_type"] for c in body["candidates"]} == {"ACTION", "DECISION"}


def test_list_requires_the_project_header(client, session_factory) -> None:
    response = client.get(f"/api/v1/meetings/{MEETING}/candidates")
    assert response.status_code == 422


def test_project_isolation_hides_another_projects_candidates(
    client, session_factory
) -> None:
    _run_meeting(session_factory)

    response = client.get(
        f"/api/v1/meetings/{MEETING}/candidates",
        headers={"X-Project-Id": "someone-else"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_get_candidate_detail(client, session_factory) -> None:
    _run_meeting(session_factory)
    listed = client.get(
        f"/api/v1/meetings/{MEETING}/candidates", headers=HEADERS
    ).json()["candidates"][0]

    response = client.get(
        f"/api/v1/candidates/{listed['candidate_id']}", headers=HEADERS
    )

    assert response.status_code == 200
    assert response.json()["candidate"]["candidate_id"] == listed["candidate_id"]


def test_unknown_candidate_is_404(client) -> None:
    response = client.get(
        "/api/v1/candidates/2f1c9a2e-0d44-4a1b-9c77-2b6e8a5d1f30", headers=HEADERS
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "CANDIDATE_NOT_FOUND"


def _action_candidate(client):
    listed = client.get(
        f"/api/v1/meetings/{MEETING}/candidates", headers=HEADERS
    ).json()["candidates"]
    return next(c for c in listed if c["suggested_type"] == "ACTION")


def test_patch_updates_title_and_bumps_version(client, session_factory) -> None:
    _run_meeting(session_factory)
    candidate = _action_candidate(client)

    response = client.patch(
        f"/api/v1/candidates/{candidate['candidate_id']}",
        headers=HEADERS,
        json={"expectedVersion": candidate["version"], "title": "고친 제목"},
    )

    assert response.status_code == 200
    updated = response.json()["candidates"][0]
    assert updated["reviewed_title"] == "고친 제목"
    assert updated["version"] == candidate["version"] + 1


def test_patch_with_a_stale_version_is_409(client, session_factory) -> None:
    _run_meeting(session_factory)
    candidate = _action_candidate(client)
    client.patch(
        f"/api/v1/candidates/{candidate['candidate_id']}",
        headers=HEADERS,
        json={"expectedVersion": candidate["version"], "title": "first"},
    )

    response = client.patch(
        f"/api/v1/candidates/{candidate['candidate_id']}",
        headers=HEADERS,
        json={"expectedVersion": candidate["version"], "title": "second"},
    )

    assert response.status_code == 409
    body = response.json()["error"]
    assert body["code"] == "VERSION_CONFLICT"
    assert body["expectedVersion"] == candidate["version"]
    assert body["actualVersion"] == candidate["version"] + 1


def test_patch_rejects_an_unknown_field(client, session_factory) -> None:
    _run_meeting(session_factory)
    candidate = _action_candidate(client)

    response = client.patch(
        f"/api/v1/candidates/{candidate['candidate_id']}",
        headers=HEADERS,
        json={"expectedVersion": candidate["version"], "notAField": 1},
    )

    assert response.status_code == 422


def test_patch_rejects_title_over_the_operational_limit(
    client,
    session_factory,
) -> None:
    _run_meeting(session_factory)
    candidate = _action_candidate(client)

    response = client.patch(
        f"/api/v1/candidates/{candidate['candidate_id']}",
        headers=HEADERS,
        json={"expectedVersion": candidate["version"], "title": "x" * 301},
    )

    assert response.status_code == 422


def test_project_header_has_a_bounded_length(client) -> None:
    response = client.get(
        f"/api/v1/meetings/{MEETING}/candidates",
        headers={"X-Project-Id": "p" * 129},
    )
    assert response.status_code == 422


def test_reject_marks_the_candidate_rejected(client, session_factory) -> None:
    _run_meeting(session_factory)
    candidate = _action_candidate(client)

    response = client.post(
        f"/api/v1/candidates/{candidate['candidate_id']}/reject",
        headers=HEADERS,
        json={"expectedVersion": candidate["version"]},
    )

    assert response.status_code == 200
    assert response.json()["candidates"][0]["review_status"] == "REJECTED"


def test_reject_is_idempotent(client, session_factory) -> None:
    _run_meeting(session_factory)
    candidate = _action_candidate(client)
    body = {"expectedVersion": candidate["version"]}
    first = client.post(
        f"/api/v1/candidates/{candidate['candidate_id']}/reject",
        headers=HEADERS,
        json=body,
    )
    second = client.post(
        f"/api/v1/candidates/{candidate['candidate_id']}/reject",
        headers=HEADERS,
        json={},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["candidates"][0]["review_status"] == "REJECTED"


def test_approve_creates_an_unattached_node(client, session_factory) -> None:
    _run_meeting(session_factory)
    candidate = _action_candidate(client)

    response = client.post(
        f"/api/v1/candidates/{candidate['candidate_id']}/approve",
        headers=HEADERS,
        json={"expectedVersion": candidate["version"]},
    )

    assert response.status_code == 200
    assert len(response.json()["createdNodeIds"]) == 1
    with session_factory() as session:
        node = session.execute(select(Node)).scalar_one()
        assert node.graph_state == "UNATTACHED"


# ------------------------------------------------------- ACTION lifecycle ---


@pytest.mark.parametrize(
    "lifecycle", ["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
)
def test_extracted_lifecycle_survives_to_the_node(
    client, session_factory, lifecycle: str
) -> None:
    """Before this change every ACTION Node was created as TODO."""

    _run_meeting(session_factory, lifecycle=lifecycle)
    candidate = _action_candidate(client)
    assert candidate["suggested_lifecycle_status"] == lifecycle
    assert candidate["effective_lifecycle_status"] == lifecycle

    client.post(
        f"/api/v1/candidates/{candidate['candidate_id']}/approve",
        headers=HEADERS,
        json={"expectedVersion": candidate["version"]},
    )

    with session_factory() as session:
        node = session.execute(
            select(Node).where(Node.source_item_id == "m1")
        ).scalar_one()
        assert node.lifecycle_status == lifecycle


def test_missing_lifecycle_falls_back_to_todo_and_flags_review(
    client, session_factory
) -> None:
    _run_meeting(session_factory, lifecycle=None)
    candidate = _action_candidate(client)

    assert candidate["suggested_lifecycle_status"] is None
    assert candidate["effective_lifecycle_status"] == "TODO"
    assert candidate["lifecycle_status_needs_review"] is True


def test_an_unparsable_lifecycle_is_ignored_rather_than_stored(
    client, session_factory
) -> None:
    _run_meeting(session_factory, lifecycle="ALMOST_DONE")
    candidate = _action_candidate(client)

    assert candidate["suggested_lifecycle_status"] is None
    assert candidate["effective_lifecycle_status"] == "TODO"


def test_reviewer_override_wins_over_the_suggestion(client, session_factory) -> None:
    _run_meeting(session_factory, lifecycle="TODO")
    candidate = _action_candidate(client)

    patched = client.patch(
        f"/api/v1/candidates/{candidate['candidate_id']}",
        headers=HEADERS,
        json={
            "expectedVersion": candidate["version"],
            "lifecycleStatus": "COMPLETED",
        },
    )
    assert patched.status_code == 200
    view = patched.json()["candidates"][0]
    assert view["reviewed_lifecycle_status"] == "COMPLETED"
    assert view["effective_lifecycle_status"] == "COMPLETED"

    client.post(
        f"/api/v1/candidates/{candidate['candidate_id']}/approve",
        headers=HEADERS,
        json={},
    )
    with session_factory() as session:
        node = session.execute(
            select(Node).where(Node.source_item_id == "m1")
        ).scalar_one()
        assert node.lifecycle_status == "COMPLETED"


def test_lifecycle_cannot_be_set_on_a_decision(client, session_factory) -> None:
    """An ACTION status must never leak onto a DECISION."""

    _run_meeting(session_factory)
    listed = client.get(
        f"/api/v1/meetings/{MEETING}/candidates", headers=HEADERS
    ).json()["candidates"]
    decision = next(c for c in listed if c["suggested_type"] == "DECISION")

    response = client.patch(
        f"/api/v1/candidates/{decision['candidate_id']}",
        headers=HEADERS,
        json={
            "expectedVersion": decision["version"],
            "lifecycleStatus": "COMPLETED",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"


def test_decision_keeps_its_own_default_lifecycle(client, session_factory) -> None:
    _run_meeting(session_factory)
    listed = client.get(
        f"/api/v1/meetings/{MEETING}/candidates", headers=HEADERS
    ).json()["candidates"]
    decision = next(c for c in listed if c["suggested_type"] == "DECISION")
    assert decision["effective_lifecycle_status"] == "ACTIVE"

    client.post(
        f"/api/v1/candidates/{decision['candidate_id']}/approve",
        headers=HEADERS,
        json={},
    )
    with session_factory() as session:
        node = session.execute(
            select(Node).where(Node.source_item_id == "m2")
        ).scalar_one()
        assert node.lifecycle_status == "ACTIVE"


def test_patch_rejects_an_invalid_lifecycle_value(client, session_factory) -> None:
    _run_meeting(session_factory)
    candidate = _action_candidate(client)

    response = client.patch(
        f"/api/v1/candidates/{candidate['candidate_id']}",
        headers=HEADERS,
        json={"expectedVersion": candidate["version"], "lifecycleStatus": "NOPE"},
    )

    assert response.status_code == 422


# ------------------------------------------- initial review -> async stage ---


def test_initial_review_complete_returns_202_and_queues_jobs(
    client, session_factory
) -> None:
    _run_meeting(session_factory)

    response = client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers=HEADERS,
        json={},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "ANALYSIS_PENDING"
    assert body["reviewedCandidateCount"] == 2
    assert body["createdNodeCount"] == 2
    assert body["queuedAnalysisJobCount"] == 2

    with session_factory() as session:
        jobs = session.execute(select(AnalysisJob)).scalars().all()
        assert len(jobs) == 2
        assert {job.status for job in jobs} == {"PENDING"}


def test_initial_review_complete_emits_outbox_events(
    client, session_factory
) -> None:
    _run_meeting(session_factory)

    client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers=HEADERS,
        json={},
    )

    with session_factory() as session:
        events = session.execute(select(OutboxEvent)).scalars().all()
        types = [event.event_type for event in events]
        assert types.count("ANALYSIS_QUEUED") == 2
        assert types.count("INITIAL_REVIEW_READY") == 1
        assert {event.status for event in events} == {"PENDING"}


def test_initial_review_complete_is_idempotent(client, session_factory) -> None:
    """Calling twice must not double-queue analysis."""

    _run_meeting(session_factory)
    client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers=HEADERS,
        json={},
    )
    second = client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers=HEADERS,
        json={},
    )

    assert second.status_code == 202
    assert second.json()["queuedAnalysisJobCount"] == 0
    with session_factory() as session:
        assert len(session.execute(select(AnalysisJob)).scalars().all()) == 2


def test_initial_review_rejects_duplicate_candidate_ids(client) -> None:
    candidate_id = "2f1c9a2e-0d44-4a1b-9c77-2b6e8a5d1f30"
    response = client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers=HEADERS,
        json={"candidateIds": [candidate_id, candidate_id]},
    )
    assert response.status_code == 422


def test_initial_review_bounds_candidate_batch_size(client) -> None:
    response = client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers=HEADERS,
        json={"candidateIds": [f"candidate-{index}" for index in range(201)]},
    )
    assert response.status_code == 422


def test_no_process_waits_for_analysis_during_the_request(
    client, session_factory
) -> None:
    """The 202 must come back with the jobs still PENDING, not already run."""

    _run_meeting(session_factory)

    response = client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers=HEADERS,
        json={},
    )

    assert response.status_code == 202
    with session_factory() as session:
        jobs = session.execute(select(AnalysisJob)).scalars().all()
        assert all(job.status == "PENDING" for job in jobs)
        assert all(job.attempt_count == 0 for job in jobs)


# ------------------------------------------------------------- status APIs ---


def test_pipeline_status_reports_stages(client, session_factory) -> None:
    _run_meeting(session_factory)

    before = client.get(
        f"/api/v1/meetings/{MEETING}/pipeline-status", headers=HEADERS
    ).json()
    assert before["pipelineStage"] == "INITIAL_REVIEW_PENDING"
    assert before["candidateCounts"]["PENDING"] == 2

    client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers=HEADERS,
        json={},
    )
    after = client.get(
        f"/api/v1/meetings/{MEETING}/pipeline-status", headers=HEADERS
    ).json()
    assert after["pipelineStage"] == "ANALYZING"
    assert after["analysisJobCounts"]["PENDING"] == 2


def test_analysis_status_lists_jobs(client, session_factory) -> None:
    _run_meeting(session_factory)
    client.post(
        f"/api/v1/meetings/{MEETING}/initial-review/complete",
        headers=HEADERS,
        json={},
    )

    response = client.get(
        f"/api/v1/meetings/{MEETING}/analysis-status", headers=HEADERS
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ANALYZING"
    assert len(body["jobs"]) == 2


def test_analysis_status_for_an_unqueued_meeting(client) -> None:
    response = client.get(
        "/api/v1/meetings/never-seen/analysis-status", headers=HEADERS
    )
    assert response.status_code == 200
    assert response.json()["status"] == "NOT_QUEUED"


def test_final_review_is_empty_before_analysis_runs(client, session_factory) -> None:
    _run_meeting(session_factory)
    response = client.get(
        f"/api/v1/meetings/{MEETING}/final-review", headers=HEADERS
    )
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_analysis_decision_response_uses_the_candidate_status() -> None:
    from types import SimpleNamespace

    from data_pipeline.api.routers.analysis import _decision_response
    from data_pipeline.contracts import AnalysisCandidateStatus

    result = SimpleNamespace(
        candidate=SimpleNamespace(status=AnalysisCandidateStatus.REJECTED),
        source_node_id="source-node",
        target_node_id=None,
        relation_id=None,
        merge_history_id=None,
    )

    response = _decision_response("analysis-candidate", result)

    assert response.status == "REJECTED"
