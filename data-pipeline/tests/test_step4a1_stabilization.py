from __future__ import annotations

import copy
import json

from sqlalchemy.exc import IntegrityError

from data_pipeline.contracts import CategorySet
from data_pipeline.llm import LLMResponse
from data_pipeline.pipeline import (
    claim_generation_request,
    generation_input_hash,
    mark_generation_failed,
    normalize_extraction_items,
    run_meeting,
)
from data_pipeline.pipeline.chain import NODE_GENERATION_PIPELINE_VERSION, estimate_credits
from data_pipeline.prompts import get_pipeline_profile
from data_pipeline.storage import (
    GraphChangeEvent,
    Node,
    NodeCandidate,
    NodeEvidence,
    Relation,
    Request,
    TranscriptSegment,
)

from .support import count


SEGMENT = {
    "segmentId": "s1",
    "startMs": 1000,
    "speakerLabel": "SPK_1",
    "text": "JWT를 인증 방식으로 최종 채택하기로 결정했습니다.",
}
RAW_ITEM = {
    "id": "m1",
    "type": "DECISION",
    "predictedCategory": "BACKEND",
    "title": "JWT 인증 채택",
    "content": "JWT를 인증 방식으로 채택한다.",
    "evidence": [{"segmentId": "s1", "quote": SEGMENT["text"]}],
}
EXTRACTION = {"meetingId": "M-STABLE", "items": [RAW_ITEM]}
JUDGMENT = {
    "meetingId": "M-STABLE",
    "judgments": [{"itemId": "m1", "result": "NEW_DECISION", "category": "BACKEND"}],
}


class SequenceClient:
    class _Settings:
        model = "fake-model"
        temperature = 0.0

    settings = _Settings()

    def __init__(self, responses, *, on_call=None):
        self.responses = list(responses)
        self.calls = 0
        self.on_call = on_call

    def complete(self, messages):
        self.calls += 1
        if self.on_call is not None:
            self.on_call(self.calls)
        if not self.responses:
            raise AssertionError("LLM must not be called")
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, LLMResponse):
            return value
        raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return LLMResponse(
            raw_response=raw,
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
            latency_ms=2,
        )


def _meeting(meeting_id: str = "M-STABLE") -> dict:
    return {
        "requestId": f"req-{meeting_id}",
        "projectId": "proj-01",
        "externalMeetingId": meeting_id,
        "segments": [copy.deepcopy(SEGMENT)],
    }


def _valid_responses(meeting_id: str) -> list[dict]:
    extraction = copy.deepcopy(EXTRACTION)
    judgment = copy.deepcopy(JUDGMENT)
    extraction["meetingId"] = meeting_id
    judgment["meetingId"] = meeting_id
    return [extraction, judgment]


def _hash(meeting_input: dict, client: SequenceClient) -> str:
    profile = get_pipeline_profile()
    return generation_input_hash(
        meeting_input=meeting_input,
        pipeline_version=NODE_GENERATION_PIPELINE_VERSION,
        profile=profile,
        category_set=CategorySet.load(),
        term_corrections=None,
        adapter_version="poc-v4-to-server-v1",
        model=client.settings.model,
        temperature=client.settings.temperature,
    )


def _assert_no_graph_writes(session_factory) -> None:
    assert count(session_factory, Node) == 0
    assert count(session_factory, NodeEvidence) == 0
    assert count(session_factory, Relation) == 0
    assert count(session_factory, GraphChangeEvent) == 0


def test_same_run_meeting_input_is_claimed_before_llm_and_returns_existing_candidates(
    session_factory,
):
    meeting_input = _meeting("M-DUPLICATE-PRECALL")
    first_client = SequenceClient(_valid_responses("M-DUPLICATE-PRECALL"))
    first = run_meeting(
        session_factory, meeting_input=meeting_input, client=first_client
    )
    second_client = SequenceClient([])
    second = run_meeting(
        session_factory, meeting_input=copy.deepcopy(meeting_input), client=second_client
    )

    assert first_client.calls == 2
    assert first.proposal_result.outcome == "NEWLY_CREATED_REVIEW_PENDING"
    assert second_client.calls == 0
    assert second.proposal_result.outcome == "DUPLICATE_REVIEW_PENDING"
    assert second.proposal_result.candidateIds == first.proposal_result.candidateIds
    assert count(session_factory, NodeCandidate) == 1


def test_changed_segment_text_for_same_meeting_rolls_back_new_candidates(
    session_factory,
):
    original = _meeting("M-REGENERATE")
    changed = copy.deepcopy(original)
    changed["segments"][0]["text"] += " 변경된 입력"

    first_client = SequenceClient(_valid_responses("M-REGENERATE"))
    second_client = SequenceClient(_valid_responses("M-REGENERATE"))
    first = run_meeting(session_factory, meeting_input=original, client=first_client)
    second = run_meeting(session_factory, meeting_input=changed, client=second_client)

    assert first.proposal_result.outcome == "NEWLY_CREATED_REVIEW_PENDING"
    assert second.proposal_result.outcome == "FAILED_PERSISTENCE"
    assert first_client.calls == second_client.calls == 2
    assert count(session_factory, Request) == 2
    assert count(session_factory, NodeCandidate) == 1
    with session_factory() as session:
        stored_segment = session.query(TranscriptSegment).one()
        assert stored_segment.raw_text == original["segments"][0]["text"]
        assert (
            stored_segment.normalized_text
            == original["segments"][0]["text"]
        )
        statuses = sorted(
            row.status for row in session.query(Request).all()
        )
        assert statuses == ["FAILED", "REVIEW_PENDING"]


def test_existing_processing_claim_returns_in_progress_without_llm(session_factory):
    meeting_input = _meeting("M-IN-PROGRESS")
    client = SequenceClient([])
    claim_generation_request(
        session_factory,
        project_id=meeting_input["projectId"],
        external_meeting_id=meeting_input["externalMeetingId"],
        external_request_id=meeting_input["requestId"],
        pipeline_version=NODE_GENERATION_PIPELINE_VERSION,
        input_hash=_hash(meeting_input, client),
    )

    result = run_meeting(session_factory, meeting_input=meeting_input, client=client)

    assert client.calls == 0
    assert result.proposal_result.status == "PROCESSING"
    assert result.proposal_result.outcome == "IN_PROGRESS"


def test_existing_failed_claim_does_not_retry_without_explicit_flag(session_factory):
    meeting_input = _meeting("M-PREVIOUSLY-FAILED")
    client = SequenceClient([])
    claim = claim_generation_request(
        session_factory,
        project_id=meeting_input["projectId"],
        external_meeting_id=meeting_input["externalMeetingId"],
        external_request_id=meeting_input["requestId"],
        pipeline_version=NODE_GENERATION_PIPELINE_VERSION,
        input_hash=_hash(meeting_input, client),
    )
    mark_generation_failed(
        session_factory,
        request_db_id=claim.request_db_id,
        stage="EXTRACTION",
        code="JSON_PARSE_ERROR",
        message="Extraction generation failed after retries",
        usage={},
    )

    result = run_meeting(session_factory, meeting_input=meeting_input, client=client)

    assert client.calls == 0
    assert result.proposal_result.outcome == "FAILED_EXTRACTION"
    assert result.proposal_result.detail["previouslyFailed"] is True

    retry_client = SequenceClient(_valid_responses("M-PREVIOUSLY-FAILED"))
    retried = run_meeting(
        session_factory,
        meeting_input=meeting_input,
        client=retry_client,
        force_retry=True,
    )
    assert retry_client.calls == 2
    assert retried.proposal_result.outcome == "NEWLY_CREATED_REVIEW_PENDING"


def test_unique_conflict_reloads_winning_claim(monkeypatch, session_factory):
    import data_pipeline.pipeline.service as service

    def commit_winner_then_raise(session, request_row):
        session.add(request_row)
        session.commit()
        raise IntegrityError("synthetic unique race", {}, Exception("winner committed"))

    monkeypatch.setattr(service, "_insert_generation_claim", commit_winner_then_raise)
    claim = claim_generation_request(
        session_factory,
        project_id="proj-01",
        external_meeting_id="M-RACE",
        external_request_id="req-M-RACE",
        pipeline_version=NODE_GENERATION_PIPELINE_VERSION,
        input_hash="a" * 64,
    )

    assert claim.outcome == "IN_PROGRESS"
    assert claim.result is not None
    assert count(session_factory, Request) == 1
    assert count(session_factory, NodeCandidate) == 0


def test_external_llm_call_runs_after_claim_transaction_is_committed(session_factory):
    meeting_input = _meeting("M-NO-OPEN-TRANSACTION")

    def write_during_external_call(call_number):
        if call_number != 1:
            return
        with session_factory() as session:
            request = session.query(Request).one()
            assert request.status == "PROCESSING"
            request.failure_message = "transaction probe"
            session.commit()

    client = SequenceClient(
        _valid_responses("M-NO-OPEN-TRANSACTION"),
        on_call=write_during_external_call,
    )
    result = run_meeting(session_factory, meeting_input=meeting_input, client=client)

    assert result.proposal_result.outcome == "NEWLY_CREATED_REVIEW_PENDING"
    with session_factory() as session:
        assert session.query(Request).one().failure_message is None


def test_extraction_parse_failure_marks_failed_and_preserves_all_attempt_usage(session_factory):
    client = SequenceClient([
        LLMResponse("not-json-1", 11, 2, 13, 3),
        LLMResponse("not-json-2", 17, 4, 21, 5),
    ])
    result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-EXTRACTION-FAILED"),
        client=client,
    )

    assert client.calls == 2
    assert result.proposal_result.status == "FAILED"
    assert result.proposal_result.outcome == "FAILED_EXTRACTION"
    assert result.proposal_result.candidateCount == 0
    assert count(session_factory, NodeCandidate) == 0
    with session_factory() as session:
        request = session.query(Request).one()
        assert request.failure_stage == "EXTRACTION"
        assert request.failure_code == "JSON_PARSE_ERROR"
        assert request.usage["inputTokens"] == 28
        assert request.usage["outputTokens"] == 6
        assert request.usage["totalTokens"] == 34
        assert request.usage["latencyMs"] == 8
        assert len(request.usage["attempts"]["extraction"]) == 2
        assert request.usage["attempts"]["judgment"] == []
    _assert_no_graph_writes(session_factory)


def test_judgment_failure_preserves_all_extraction_candidates_conservatively(session_factory):
    extraction = {
        "meetingId": "M-JUDGMENT-FAILED",
        "items": [
            RAW_ITEM,
            {
                **RAW_ITEM,
                "id": "m2",
                "type": "ACTION",
                "title": "문서화",
            },
        ],
    }
    client = SequenceClient([extraction, "bad judgment 1", "bad judgment 2"])
    result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-JUDGMENT-FAILED"),
        client=client,
    )

    assert client.calls == 3
    assert result.proposal_result.outcome == "REVIEW_PENDING_WITH_JUDGMENT_WARNING"
    assert result.proposal_result.warnings == ["JUDGMENT_FAILED"]
    assert result.proposal_result.candidateCount == 2
    with session_factory() as session:
        rows = session.query(NodeCandidate).all()
        assert len(rows) == 2
        assert {row.suggested_disposition for row in rows} == {"MINUTES_ONLY"}
        assert {row.suggested_reason for row in rows} == {"JUDGMENT_FAILED"}
        assert all(row.suggested_parent_candidate_id is None for row in rows)
        request = session.query(Request).one()
        assert request.status == "REVIEW_PENDING"
        assert request.failure_stage == "JUDGMENT"
        assert request.warnings == ["JUDGMENT_FAILED"]
    _assert_no_graph_writes(session_factory)


def test_persistence_failure_rolls_back_candidates_and_marks_request_failed(
    monkeypatch, session_factory
):
    import data_pipeline.pipeline.chain as chain

    def fail_persistence(*args, **kwargs):
        raise RuntimeError("synthetic persistence failure")

    monkeypatch.setattr(chain, "finalize_generation_candidates", fail_persistence)
    result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-PERSISTENCE-FAILED"),
        client=SequenceClient(_valid_responses("M-PERSISTENCE-FAILED")),
    )

    assert result.proposal_result.outcome == "FAILED_PERSISTENCE"
    assert count(session_factory, NodeCandidate) == 0
    with session_factory() as session:
        request = session.query(Request).one()
        assert request.status == "FAILED"
        assert request.failure_stage == "PERSISTENCE"
        assert request.failure_code == "CANDIDATE_PERSISTENCE_FAILED"
        assert request.raw_extraction is not None
        assert request.raw_judgment is not None
    _assert_no_graph_writes(session_factory)


def test_retry_usage_sums_failed_extraction_attempt_success_and_judgment(session_factory):
    valid_extraction, valid_judgment = [
        json.dumps(value, ensure_ascii=False)
        for value in _valid_responses("M-USAGE-RETRY")
    ]
    client = SequenceClient([
        LLMResponse("bad extraction", 10, 1, 11, 2),
        LLMResponse(valid_extraction, 20, 2, 22, 3),
        LLMResponse(valid_judgment, 30, 3, 33, 4),
    ])

    result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-USAGE-RETRY"),
        client=client,
    )

    assert result.proposal_result.status == "REVIEW_PENDING"
    with session_factory() as session:
        usage = session.query(Request).one().usage
        assert usage["inputTokens"] == 60
        assert usage["outputTokens"] == 6
        assert usage["totalTokens"] == 66
        assert usage["latencyMs"] == 9
        assert usage["credits"] == round(
            estimate_credits(10, 1)
            + estimate_credits(20, 2)
            + estimate_credits(30, 3),
            4,
        )
        assert [a["success"] for a in usage["attempts"]["extraction"]] == [False, True]
        assert [a["success"] for a in usage["attempts"]["judgment"]] == [True]


def test_invalid_extraction_envelope_retries_then_fails_without_candidates(session_factory):
    invalid = {"meetingId": "M-BAD-EXTRACTION", "foo": "bar"}
    client = SequenceClient([invalid, invalid])

    result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-BAD-EXTRACTION"),
        client=client,
    )

    assert client.calls == 2
    assert result.proposal_result.outcome == "FAILED_EXTRACTION"
    assert result.proposal_result.candidateCount == 0
    with session_factory() as session:
        request = session.query(Request).one()
        assert request.failure_stage == "EXTRACTION"
        assert request.failure_code == "INVALID_EXTRACTION_SCHEMA"
        assert [
            attempt["errorCode"]
            for attempt in request.usage["runs"][0]["stages"]["extraction"]["attempts"]
        ] == ["INVALID_EXTRACTION_SCHEMA", "INVALID_EXTRACTION_SCHEMA"]
    assert count(session_factory, NodeCandidate) == 0


def test_explicit_empty_extraction_envelope_is_a_valid_empty_meeting(session_factory):
    client = SequenceClient([
        {"meetingId": "M-EMPTY", "items": []},
        {"meetingId": "M-EMPTY", "judgments": []},
    ])

    result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-EMPTY"),
        client=client,
    )

    assert client.calls == 2
    assert result.proposal_result.status == "REVIEW_PENDING"
    assert result.proposal_result.candidateCount == 0


def test_extraction_meeting_id_mismatch_retries_with_specific_code(session_factory):
    mismatch = {"meetingId": "OTHER", "items": []}
    client = SequenceClient([mismatch, mismatch])

    result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-MISMATCH"),
        client=client,
    )

    assert client.calls == 2
    assert result.proposal_result.outcome == "FAILED_EXTRACTION"
    with session_factory() as session:
        request = session.query(Request).one()
        assert request.failure_code == "MEETING_ID_MISMATCH"
        assert {
            attempt["errorCode"]
            for attempt in request.usage["runs"][0]["stages"]["extraction"]["attempts"]
        } == {"MEETING_ID_MISMATCH"}


def test_invalid_judgment_envelope_retries_and_preserves_candidates(session_factory):
    extraction = _valid_responses("M-BAD-JUDGMENT")[0]
    invalid = {"meetingId": "M-BAD-JUDGMENT", "foo": "bar"}
    client = SequenceClient([extraction, invalid, invalid])

    result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-BAD-JUDGMENT"),
        client=client,
    )

    assert client.calls == 3
    assert result.proposal_result.outcome == "REVIEW_PENDING_WITH_JUDGMENT_WARNING"
    assert result.proposal_result.warnings == ["JUDGMENT_FAILED"]
    with session_factory() as session:
        candidate = session.query(NodeCandidate).one()
        request = session.query(Request).one()
        assert candidate.suggested_disposition == "MINUTES_ONLY"
        assert candidate.suggested_reason == "JUDGMENT_FAILED"
        assert candidate.suggested_parent_candidate_id is None
        assert request.failure_stage == "JUDGMENT"
        assert request.failure_code == "INVALID_JUDGMENT_SCHEMA"


def test_non_array_stage_collections_are_schema_failures(session_factory):
    extraction_client = SequenceClient([
        {"meetingId": "M-NONARRAY-EXTRACTION", "items": {}},
        {"meetingId": "M-NONARRAY-EXTRACTION", "items": [RAW_ITEM, "bad"]},
    ])
    extraction_result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-NONARRAY-EXTRACTION"),
        client=extraction_client,
    )
    assert extraction_result.proposal_result.detail["failureCode"] == (
        "INVALID_EXTRACTION_SCHEMA"
    )

    judgment_client = SequenceClient([
        {"meetingId": "M-NONARRAY-JUDGMENT", "items": [RAW_ITEM]},
        {"meetingId": "M-NONARRAY-JUDGMENT", "judgments": {}},
        {"meetingId": "M-NONARRAY-JUDGMENT", "judgments": "bad"},
    ])
    judgment_result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-NONARRAY-JUDGMENT"),
        client=judgment_client,
    )
    assert judgment_result.proposal_result.status == "REVIEW_PENDING"
    with session_factory() as session:
        judgment_request = session.query(Request).filter_by(
            external_meeting_id="M-NONARRAY-JUDGMENT"
        ).one()
        assert judgment_request.failure_code == "INVALID_JUDGMENT_SCHEMA"


def test_different_request_id_for_same_input_reuses_original_request(session_factory):
    first_input = _meeting("M-REQUEST-ID")
    second_input = copy.deepcopy(first_input)
    second_input["requestId"] = "req-second"
    first_client = SequenceClient(_valid_responses("M-REQUEST-ID"))
    second_client = SequenceClient([])

    first = run_meeting(session_factory, meeting_input=first_input, client=first_client)
    second = run_meeting(session_factory, meeting_input=second_input, client=second_client)

    assert second_client.calls == 0
    assert second.proposal_result.outcome == "DUPLICATE_REVIEW_PENDING"
    assert second.proposal_result.candidateIds == first.proposal_result.candidateIds
    with session_factory() as session:
        request = session.query(Request).one()
        assert request.external_request_id == first_input["requestId"]


def test_same_transcript_with_different_model_allows_new_generation(session_factory):
    meeting_input = _meeting("M-MODEL-CHANGE")
    first_client = SequenceClient(_valid_responses("M-MODEL-CHANGE"))
    second_client = SequenceClient(_valid_responses("M-MODEL-CHANGE"))
    second_client.settings = type(
        "Settings", (), {"model": "different-model", "temperature": 0.0}
    )()

    run_meeting(session_factory, meeting_input=meeting_input, client=first_client)
    run_meeting(session_factory, meeting_input=meeting_input, client=second_client)

    assert first_client.calls == second_client.calls == 2
    assert count(session_factory, Request) == 2


def test_same_transcript_with_different_profile_allows_new_generation(session_factory):
    meeting_input = _meeting("M-PROFILE-CHANGE")
    first_client = SequenceClient(_valid_responses("M-PROFILE-CHANGE"))
    second_client = SequenceClient(_valid_responses("M-PROFILE-CHANGE"))

    run_meeting(session_factory, meeting_input=meeting_input, client=first_client)
    run_meeting(
        session_factory,
        meeting_input=meeting_input,
        client=second_client,
        prompt_profile="m2-current-candidate",
    )

    assert first_client.calls == second_client.calls == 2
    assert count(session_factory, Request) == 2


def test_force_retry_preserves_failed_run_and_accumulates_usage(session_factory):
    meeting_input = _meeting("M-FORCE-USAGE")
    failed_client = SequenceClient([
        LLMResponse("bad-1", 50, 0, 50, 3),
        LLMResponse("bad-2", 50, 0, 50, 5),
    ])

    failed = run_meeting(
        session_factory,
        meeting_input=meeting_input,
        client=failed_client,
    )
    assert failed.proposal_result.status == "FAILED"
    with session_factory() as session:
        first_usage = copy.deepcopy(session.query(Request).one().usage)
    assert first_usage["credits"] == 1.75
    assert len(first_usage["runs"]) == 1
    assert first_usage["runs"][0]["status"] == "FAILED"

    extraction, judgment = _valid_responses("M-FORCE-USAGE")
    retry_client = SequenceClient([
        LLMResponse(json.dumps(extraction), 50, 0, 50, 7),
        LLMResponse(json.dumps(judgment), 50, 0, 50, 11),
    ])
    retried = run_meeting(
        session_factory,
        meeting_input=meeting_input,
        client=retry_client,
        force_retry=True,
    )

    assert retried.proposal_result.status == "REVIEW_PENDING"
    with session_factory() as session:
        usage = session.query(Request).one().usage
        assert usage["schemaVersion"] == "request-usage-v2"
        assert usage["credits"] == 3.5
        assert usage["inputTokens"] == 200
        assert usage["totalTokens"] == 200
        assert usage["latencyMs"] == 26
        assert len(usage["runs"]) == 2
        assert [run["runAttempt"] for run in usage["runs"]] == [1, 2]
        assert [run["status"] for run in usage["runs"]] == [
            "FAILED",
            "REVIEW_PENDING",
        ]
        assert usage["runs"][0] == first_usage["runs"][0]


def test_failed_request_without_force_retry_keeps_usage_and_skips_llm(session_factory):
    meeting_input = _meeting("M-NO-FORCE-USAGE")
    failed_client = SequenceClient(["bad-1", "bad-2"])
    run_meeting(
        session_factory,
        meeting_input=meeting_input,
        client=failed_client,
    )
    with session_factory() as session:
        before = copy.deepcopy(session.query(Request).one().usage)

    duplicate_client = SequenceClient([])
    duplicate = run_meeting(
        session_factory,
        meeting_input=meeting_input,
        client=duplicate_client,
    )

    assert duplicate_client.calls == 0
    assert duplicate.proposal_result.outcome == "FAILED_EXTRACTION"
    with session_factory() as session:
        assert session.query(Request).one().usage == before


def test_oversized_unknown_model_values_are_raw_preserved_and_relationally_safe(
    session_factory,
):
    long_id = "raw-id-" + "x" * 500
    long_type = "UNKNOWN-TYPE-" + "y" * 500
    long_reason = "reason-" + "r" * 1000
    long_category = "category-" + "c" * 500
    raw_items = [
        {
            **RAW_ITEM,
            "id": long_id,
            "type": long_type,
            "predictedCategory": long_category,
        },
        {
            **RAW_ITEM,
            "id": long_id,
            "type": "ISSUE",
            "title": "두 번째 중복 ID",
        },
        {
            **RAW_ITEM,
            "id": "m3",
            "type": "DECISION",
            "title": "긴 카테고리",
        },
    ]
    normalized = normalize_extraction_items(raw_items)
    judgments = {
        "meetingId": "M-OVERSIZED",
        "judgments": [
            {
                "itemId": normalized[0]["id"],
                "result": "MINUTES_ONLY",
                "reason": long_reason,
            },
            {
                "itemId": normalized[1]["id"],
                "result": "MINUTES_ONLY",
                "reason": long_reason,
            },
            {
                "itemId": normalized[2]["id"],
                "result": "NEW_DECISION",
                "category": long_category,
            },
        ],
    }
    client = SequenceClient([
        {"meetingId": "M-OVERSIZED", "items": raw_items},
        judgments,
    ])
    result = run_meeting(
        session_factory,
        meeting_input=_meeting("M-OVERSIZED"),
        client=client,
        prompt_profile="m2-current-candidate",
    )

    assert result.proposal_result.candidateCount == 3
    with session_factory() as session:
        rows = session.query(NodeCandidate).order_by(NodeCandidate.created_at).all()
        assert len({row.source_item_id for row in rows}) == 3
        assert all(len(row.source_item_id) <= 64 for row in rows)
        assert rows[0].raw_item["id"] == long_id
        assert rows[1].raw_item["id"] == long_id
        assert rows[0].raw_item["type"] == long_type
        assert rows[0].suggested_node_type == "UNKNOWN"
        assert rows[1].suggested_reason == long_reason
        assert rows[1].raw_judgment["reason"] == long_reason
        assert len(rows[2].suggested_category) == 64
        assert rows[2].raw_judgment["category"] == long_category
    _assert_no_graph_writes(session_factory)
