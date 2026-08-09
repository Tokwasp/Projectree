"""node_analysis_run state after a B-model failure in the automatic pipeline.

Regression suite for the incident where a GMS HTTP 400 was persisted as
``b_model_status=SKIPPED`` / ``NO_VALID_B_MODEL_RESULT`` with both failure
columns NULL, making a hard external-API outage indistinguishable from "there
was nothing to recommend".

Contract under test:
  SUCCEEDED - a validated decision exists.
  FAILED    - the provider was called and did not deliver one.
  SKIPPED   - the provider was deliberately not called.
"""

from __future__ import annotations

import uuid

import httpx
from sqlalchemy import select

from data_pipeline.b_model.failures import (
    FAILURE_HTTP_ERROR,
    FAILURE_INVALID_RESPONSE,
    FAILURE_TIMEOUT,
    FAILURE_TRANSPORT_ERROR,
    FAILURE_UNCLASSIFIED,
    FAILURE_VALIDATION_ERROR,
)
from data_pipeline.b_model.gms import BModelClientSettings, GmsBModelClient
from data_pipeline.pipeline.automatic_graph import (
    AutoMergePolicy,
    run_automatic_graph,
)
from data_pipeline.storage import BModelResult, Node, NodeAnalysisRun

from tests.test_automatic_graph import (  # shared seeding helpers
    TypeEmbedding,
    _seed_candidate,
    _seed_existing_decision,
    _seed_generation_run,
    _seed_request,
    _settings,
)

PROVIDER_MODEL = "gpt-5.2"


class _FailingB:
    """B-model client whose transport always fails the same way."""

    provider_model = PROVIDER_MODEL

    def __init__(self, error: Exception):
        self._error = error
        self.calls = 0

    def recommend(self, *, source_node, retrieval_candidates):
        del source_node, retrieval_candidates
        self.calls += 1
        raise self._error


class _CreateNewB:
    provider_model = PROVIDER_MODEL

    def recommend(self, *, source_node, retrieval_candidates):
        del retrieval_candidates
        return {
            "recommendation": "CREATE_NEW",
            "targetNodeId": None,
            "relationType": None,
            "suggestedTitle": source_node["title"],
            "suggestedContent": source_node.get("content", ""),
            "reason": "독립 노드로 유지",
            "metadata": {},
        }


class _ShapeViolatingB:
    """Answers, but violates the BModelDecision contract."""

    provider_model = PROVIDER_MODEL

    def recommend(self, *, source_node, retrieval_candidates):
        del source_node, retrieval_candidates
        return {"recommendation": "CREATE_NEW"}


def _gms_client_returning(status: int, body: dict) -> GmsBModelClient:
    """A real GMS client over a mock transport, so the 400 path is exercised."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    return GmsBModelClient(
        BModelClientSettings(
            api_key="test-key-not-a-real-secret",
            base_url="https://gateway.invalid/v1",
            model=PROVIDER_MODEL,
            retry_count=0,
            retry_backoff_seconds=0.0,
        ),
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )


def _run(session_factory, *, b_model_client, project: str, meeting: str, seed_target: bool):
    """One meeting with a single DECISION candidate through the auto pipeline."""

    if seed_target:
        _seed_existing_decision(
            session_factory,
            project=project,
            title="회의 처리 서버는 EC2를 사용한다",
        )
    request_id = _seed_request(session_factory, project=project, meeting=meeting)
    candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="회의 처리 서버는 EC2를 사용한다",
    )
    run_id = _seed_generation_run(session_factory, project=project, meeting=meeting)
    result = run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(candidate_id)],
        embedding_client=TypeEmbedding(),
        b_model_client=b_model_client,
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(min_similarity=0.9, min_margin=0.1),
    )
    return result, candidate_id


def _analysis_run(session_factory, candidate_id: uuid.UUID) -> NodeAnalysisRun:
    with session_factory() as session:
        node = session.execute(
            select(Node).where(Node.source_candidate_id == candidate_id)
        ).scalar_one()
        return session.execute(
            select(NodeAnalysisRun).where(
                NodeAnalysisRun.source_node_id == node.id
            )
        ).scalar_one()


# ------------------------------------------------------- D: HTTP 400 -> FAILED ---


def test_http_400_is_recorded_as_failed_not_skipped(session_factory):
    client = _gms_client_returning(
        400, {"error": {"message": "invalid model", "code": "model_not_found"}}
    )
    _, candidate_id = _run(
        session_factory,
        b_model_client=client,
        project="p-400",
        meeting="m-400",
        seed_target=True,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert run.retrieval_status == "COMPLETED"
    assert run.retrieval_result_count > 0
    assert run.b_model_status == "FAILED"
    assert run.b_model_skip_reason is None
    assert run.b_model_failure_code == FAILURE_HTTP_ERROR
    assert "status=400" in run.b_model_failure_message
    assert "invalid model" in run.b_model_failure_message


def test_persisted_failure_message_never_contains_the_api_key(session_factory):
    client = _gms_client_returning(400, {"error": {"message": "invalid model"}})
    _, candidate_id = _run(
        session_factory,
        b_model_client=client,
        project="p-400-safe",
        meeting="m-400-safe",
        seed_target=True,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert "test-key-not-a-real-secret" not in run.b_model_failure_message
    assert "Bearer" not in run.b_model_failure_message


# ------------------------------------------- F/G: other real execution failures ---


def test_an_unclassified_client_error_is_still_recorded_as_failed(
    session_factory,
):
    """An unattributable error gets its own code, not a network diagnosis.

    Transport classification belongs to the adapter that owns the transport.
    Anything else must still land as FAILED rather than as a silent skip, but
    must NOT claim to be a transport problem - a local AttributeError would
    otherwise send an operator to check the network.
    """

    client = _FailingB(RuntimeError("adapter exploded"))
    _, candidate_id = _run(
        session_factory,
        b_model_client=client,
        project="p-unclassified",
        meeting="m-unclassified",
        seed_target=True,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert client.calls == 1
    assert run.b_model_status == "FAILED"
    assert run.b_model_skip_reason is None
    assert run.b_model_failure_code == FAILURE_UNCLASSIFIED
    assert run.b_model_failure_code != FAILURE_TRANSPORT_ERROR
    assert "adapter exploded" in run.b_model_failure_message


def test_timeout_from_the_real_adapter_is_recorded_as_a_timeout(session_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    client = GmsBModelClient(
        BModelClientSettings(
            api_key="k",
            base_url="https://gateway.invalid/v1",
            model=PROVIDER_MODEL,
            retry_count=0,
            retry_backoff_seconds=0.0,
        ),
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )
    _, candidate_id = _run(
        session_factory,
        b_model_client=client,
        project="p-timeout-real",
        meeting="m-timeout-real",
        seed_target=True,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert run.b_model_status == "FAILED"
    assert run.b_model_failure_code == FAILURE_TIMEOUT


def test_invalid_decision_shape_is_a_validation_failure(session_factory):
    _, candidate_id = _run(
        session_factory,
        b_model_client=_ShapeViolatingB(),
        project="p-shape",
        meeting="m-shape",
        seed_target=True,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert run.b_model_status == "FAILED"
    assert run.b_model_failure_code == FAILURE_VALIDATION_ERROR
    assert run.b_model_skip_reason is None


def test_unusable_provider_body_is_an_invalid_response_failure(session_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    client = GmsBModelClient(
        BModelClientSettings(
            api_key="k",
            base_url="https://gateway.invalid/v1",
            model=PROVIDER_MODEL,
            retry_count=0,
            retry_backoff_seconds=0.0,
        ),
        transport=httpx.MockTransport(handler),
        sleep=lambda _s: None,
    )
    _, candidate_id = _run(
        session_factory,
        b_model_client=client,
        project="p-nochoices",
        meeting="m-nochoices",
        seed_target=True,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert run.b_model_status == "FAILED"
    assert run.b_model_failure_code == FAILURE_INVALID_RESPONSE


# --------------------------------------------------- H: genuine skips stay SKIPPED ---


def test_no_retrieval_candidates_is_still_a_skip(session_factory):
    client = _FailingB(AssertionError("must not be called"))
    _, candidate_id = _run(
        session_factory,
        b_model_client=client,
        project="p-skip",
        meeting="m-skip",
        seed_target=False,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert client.calls == 0
    assert run.retrieval_result_count == 0
    assert run.b_model_status == "SKIPPED"
    assert run.b_model_skip_reason == "NO_RETRIEVAL_CANDIDATES"
    assert run.b_model_failure_code is None
    assert run.b_model_failure_message is None


# ------------------------------------------------------ success path unchanged ---


def test_successful_recommendation_records_the_provider_model(session_factory):
    _, candidate_id = _run(
        session_factory,
        b_model_client=_CreateNewB(),
        project="p-ok",
        meeting="m-ok",
        seed_target=True,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert run.b_model_status == "SUCCEEDED"
    assert run.b_model_skip_reason is None
    assert run.b_model_failure_code is None

    with session_factory() as session:
        persisted = session.execute(
            select(BModelResult).where(BModelResult.analysis_run_id == run.id)
        ).scalar_one()
    # model = provider model; the execution label lives in metadata only.
    assert persisted.model == PROVIDER_MODEL
    assert persisted.model_version == "automatic-v1"
    assert persisted.metadata_json["pipelineLabel"] == "automatic-b-model"


# ------------------------------------------------------------- I: regression ---


def test_b_model_failure_is_not_reported_as_a_clean_create_new(session_factory):
    """A provider outage must not look like a successful CREATE_NEW decision.

    The Node is still published (the meeting has to make progress), but the run
    row has to say the B model failed - otherwise a repeated outage silently
    re-creates the same semantic Node on every meeting with nothing to alert on.
    """

    client = _gms_client_returning(400, {"error": {"message": "invalid model"}})
    result, candidate_id = _run(
        session_factory,
        b_model_client=client,
        project="p-regression",
        meeting="m-regression",
        seed_target=True,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert run.b_model_status != "SUCCEEDED"
    assert run.b_model_status == "FAILED"
    assert run.b_model_skip_reason != "NO_VALID_B_MODEL_RESULT"

    # No decision was made, so nothing was merged or linked.
    assert result.merge_operation_ids == ()
    assert result.relation_ids == ()
    with session_factory() as session:
        assert (
            session.execute(
                select(BModelResult).where(
                    BModelResult.analysis_run_id == run.id
                )
            ).scalar_one_or_none()
            is None
        )

    # The failure is visible in the generation-run warnings too.
    codes = {warning["code"] for warning in result.warnings}
    assert "B_MODEL_FAILED_CREATE_NEW" in codes
    failure = next(
        warning
        for warning in result.warnings
        if warning["code"] == "B_MODEL_FAILED_CREATE_NEW"
    )
    assert failure["failureCode"] == FAILURE_HTTP_ERROR
    assert "invalid model" in failure["failureMessage"]


# ------------------------------- run-level columns and the retrieval stage ---


def test_b_model_failure_is_findable_by_the_run_level_failure_columns(
    session_factory,
):
    """`WHERE failure_code IS NOT NULL` must not return zero rows in an outage.

    node_analysis_run.status stays COMPLETED (the Node was published), so the
    run-level failure columns are what makes the outage findable at all.
    """

    client = _gms_client_returning(400, {"error": {"message": "invalid model"}})
    _, candidate_id = _run(
        session_factory,
        b_model_client=client,
        project="p-runcols",
        meeting="m-runcols",
        seed_target=True,
    )

    run = _analysis_run(session_factory, candidate_id)
    assert run.failure_code == FAILURE_HTTP_ERROR
    assert run.failure_message
    assert "status=400" in run.failure_message


class _FailingEmbedding:
    """Embedding client that fails the way a rotated key would."""

    def embed(self, *, text: str, model: str, dimensions: int):
        del text, model, dimensions
        raise RuntimeError("embedding provider rejected the request: 401")


def test_retrieval_stage_failure_is_a_skip_with_its_own_reason(session_factory):
    """Retrieval never completed, so the B model was never attempted."""

    project, meeting = "p-retrfail", "m-retrfail"
    request_id = _seed_request(session_factory, project=project, meeting=meeting)
    candidate_id = _seed_candidate(
        session_factory,
        request_id=request_id,
        project=project,
        meeting=meeting,
        item_id="item-1",
        node_type="DECISION",
        title="회의 처리 서버는 EC2를 사용한다",
    )
    run_id = _seed_generation_run(session_factory, project=project, meeting=meeting)
    b_model = _FailingB(AssertionError("must not be called"))

    run_automatic_graph(
        session_factory,
        generation_run_id=run_id,
        project_id=project,
        external_meeting_id=meeting,
        candidate_ids=[str(candidate_id)],
        embedding_client=_FailingEmbedding(),
        b_model_client=b_model,
        retrieval_settings=_settings(),
        merge_policy=AutoMergePolicy(min_similarity=0.9, min_margin=0.1),
    )

    run = _analysis_run(session_factory, candidate_id)
    assert b_model.calls == 0
    assert run.retrieval_status == "FAILED"
    assert run.retrieval_completed_at is None
    assert run.b_model_status == "SKIPPED"
    assert run.b_model_skip_reason == "RETRIEVAL_FAILED"
    assert run.b_model_failure_code is None
    # The embedding provider's own reason is preserved, not just a class name.
    assert run.failure_code == "RETRIEVAL_FAILED"
    assert "401" in run.failure_message
