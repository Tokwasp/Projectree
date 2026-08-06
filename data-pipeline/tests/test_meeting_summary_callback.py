from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import select

from data_pipeline.meeting_analysis.coordinator import MeetingAnalysisCoordinator
from data_pipeline.meeting_analysis.result_events import stage_task_failed_v3
from data_pipeline.meeting_analysis.runtime_adapters import summary_processor
from data_pipeline.meeting_summary import (
    CallbackResult,
    FakeMeetingSummaryGenerator,
    GeneratedMeetingSummary,
    MeetingRecordCallbackClient,
    MeetingSummaryContractError,
    MeetingSummaryResult,
    PermanentMeetingRecordCallbackError,
    RetryableMeetingRecordCallbackError,
    build_callback_body,
    compact_callback_body,
    json_array_size_bytes,
    load_meeting_record_callback_settings,
    normalize_generated_summary,
    normalize_summary_items,
)
from data_pipeline.storage import (
    Meeting,
    MeetingAnalysisCommand,
    MeetingAnalysisTask,
    MeetingSummary,
    OutboxEvent,
    RecordingReadyEvent,
    TranscriptSegment,
)

COMMAND_ID = uuid.UUID("0fcaeb2d-8f50-4ced-a081-54faf4de9f37")
PROJECT_ID = "3"
MEETING_ID = "35"


def _result(*, structured: dict, body: str = "") -> MeetingSummaryResult:
    return MeetingSummaryResult(
        summary_id=uuid.uuid4(),
        project_id=PROJECT_ID,
        external_meeting_id=MEETING_ID,
        summary_version=1,
        source_hash="a" * 64,
        title="회의 제목",
        body=body,
        structured_summary=structured,
        status="READY",
        generator_name="fake",
        generator_version="1",
        created_at=datetime.now(timezone.utc),
    )


def _success_response(*, duplicated: bool) -> dict:
    return {
        "status": 200,
        "message": "성공",
        "data": {
            "meetingRecordId": 91,
            "meetingId": 35,
            "commandId": str(COMMAND_ID),
            "version": 0,
            "duplicated": duplicated,
        },
    }


def _http_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _callback_client(handler, *, sleeps: list[float] | None = None):
    recorded_sleeps = sleeps if sleeps is not None else []
    return MeetingRecordCallbackClient(
        base_url="https://java.example/",
        api_key="not-a-real-secret",
        timeout_seconds=10,
        http_client=_http_client(handler),
        sleep=recorded_sleeps.append,
    )


def test_callback_body_maps_current_and_legacy_storage_without_extra_fields():
    current = build_callback_body(
        _result(
            structured={
                "summary": ["핵심 논의를 정리했다."],
                "decisions": ["PostgreSQL을 사용한다."],
                "nextTodos": ["배포 문서를 작성한다."],
                "issues": [],
            }
        ),
        command_id=COMMAND_ID,
    )
    legacy = build_callback_body(
        _result(
            body="기존 본문",
            structured={
                "decisions": ["기존 결정"],
                "actions": ["기존 할 일"],
                "issues": ["기존 이슈"],
            },
        ),
        command_id=COMMAND_ID,
    )

    assert current == {
        "callbackSchemaVersion": 1,
        "commandId": str(COMMAND_ID),
        "title": "회의 제목",
        "summary": ["핵심 논의를 정리했다."],
        "decisions": ["PostgreSQL을 사용한다."],
        "nextTodos": ["배포 문서를 작성한다."],
        "issues": [],
    }
    assert legacy["summary"] == ["기존 본문"]
    assert legacy["nextTodos"] == ["기존 할 일"]
    assert set(current) == {
        "callbackSchemaVersion",
        "commandId",
        "title",
        "summary",
        "decisions",
        "nextTodos",
        "issues",
    }


@pytest.mark.parametrize("duplicated", [False, True])
def test_callback_put_contract_and_duplicate_success(duplicated: bool):
    requests: list[httpx.Request] = []
    body = build_callback_body(
        _result(
            structured={
                "summary": [],
                "decisions": [],
                "nextTodos": [],
                "issues": [],
            }
        ),
        command_id=COMMAND_ID,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_success_response(duplicated=duplicated))

    result = _callback_client(handler).send(
        meeting_id=MEETING_ID,
        body=body,
        project_id=PROJECT_ID,
    )

    assert result == CallbackResult(91, MEETING_ID, str(COMMAND_ID), 0, duplicated)
    assert requests[0].method == "PUT"
    assert requests[0].url.path == "/api/internal/meetings/35/record"
    assert requests[0].headers["X-Internal-Api-Key"] == "not-a-real-secret"
    assert json.loads(requests[0].content) == body


def test_callback_retries_5xx_with_identical_payload_and_fixed_delays():
    payloads: list[dict] = []
    sleeps: list[float] = []
    statuses = iter([500, 502, 503, 200])
    body = build_callback_body(
        _result(
            structured={
                "summary": ["요약"],
                "decisions": [],
                "nextTodos": [],
                "issues": [],
            }
        ),
        command_id=COMMAND_ID,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        status = next(statuses)
        if status == 200:
            return httpx.Response(200, json=_success_response(duplicated=False))
        return httpx.Response(status, json={"errorCode": "TEMPORARY"})

    result = _callback_client(handler, sleeps=sleeps).send(
        meeting_id=MEETING_ID,
        body=body,
    )

    assert result.duplicated is False
    assert sleeps == [1.0, 2.0, 4.0]
    assert payloads == [body, body, body, body]


def test_callback_retries_network_errors_then_reports_delivery_failure():
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(RetryableMeetingRecordCallbackError):
        _callback_client(handler, sleeps=sleeps).send(
            meeting_id=MEETING_ID,
            body={"commandId": str(COMMAND_ID)},
        )
    assert calls == 4
    assert sleeps == [1.0, 2.0, 4.0]


@pytest.mark.parametrize(
    "response_body",
    [
        {"data": {"meetingRecordId": 91, "meetingId": 35}},
        {
            "data": {
                "meetingRecordId": 91,
                "meetingId": 35,
                "commandId": str(uuid.uuid4()),
                "version": 0,
                "duplicated": False,
            }
        },
        {
            "data": {
                "meetingRecordId": 91,
                "meetingId": 35,
                "commandId": str(COMMAND_ID),
                "version": 0,
                "duplicated": "false",
            }
        },
        {
            "data": {
                "meetingRecordId": 91,
                "meetingId": 999,
                "commandId": str(COMMAND_ID),
                "version": 0,
                "duplicated": False,
            }
        },
    ],
)
def test_callback_rejects_malformed_or_mismatched_success(response_body):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=response_body)

    with pytest.raises(PermanentMeetingRecordCallbackError):
        _callback_client(handler).send(
            meeting_id=MEETING_ID,
            body={"commandId": str(COMMAND_ID)},
        )


def test_callback_rejects_non_json_success_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    with pytest.raises(PermanentMeetingRecordCallbackError):
        _callback_client(handler).send(
            meeting_id=MEETING_ID,
            body={"commandId": str(COMMAND_ID)},
        )


def test_callback_exhausts_5xx_after_four_identical_requests():
    payloads: list[dict] = []
    sleeps: list[float] = []
    body = {"commandId": str(COMMAND_ID), "summary": ["same"]}

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(503, json={"errorCode": "UNAVAILABLE"})

    with pytest.raises(RetryableMeetingRecordCallbackError):
        _callback_client(handler, sleeps=sleeps).send(
            meeting_id=MEETING_ID,
            body=body,
        )
    assert payloads == [body, body, body, body]
    assert sleeps == [1.0, 2.0, 4.0]


@pytest.mark.parametrize("status", [400, 401, 404, 409])
def test_callback_does_not_retry_4xx(status: int):
    calls = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            status,
            json={"errorCode": "REJECTED", "errorMessage": "rejected"},
        )

    with pytest.raises(PermanentMeetingRecordCallbackError):
        _callback_client(handler, sleeps=sleeps).send(
            meeting_id=MEETING_ID,
            body={"commandId": str(COMMAND_ID)},
        )
    assert calls == 1
    assert sleeps == []


def test_already_failed_is_rejected_once_and_written_as_warning(caplog):
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            409,
            json={
                "errorCode": "MEETING_RECORD_SUMMARY_ALREADY_FAILED",
                "errorMessage": "already failed",
            },
        )

    with caplog.at_level("WARNING"), pytest.raises(
        PermanentMeetingRecordCallbackError
    ) as captured:
        _callback_client(handler).send(
            meeting_id=MEETING_ID,
            body={"commandId": str(COMMAND_ID)},
        )

    assert captured.value.error_code == "MEETING_RECORD_SUMMARY_ALREADY_FAILED"
    assert calls == 1
    assert "MEETING_RECORD_SUMMARY_ALREADY_FAILED" in caplog.text


def test_callback_logs_do_not_expose_api_key_or_full_body(caplog):
    api_key = "super-secret-callback-key"
    private_summary = "do-not-log-this-summary-content"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"errorCode": "INVALID_REQUEST", "errorMessage": "rejected"},
        )

    client = MeetingRecordCallbackClient(
        base_url="https://java.example",
        api_key=api_key,
        http_client=_http_client(handler),
        sleep=lambda _: None,
    )
    with caplog.at_level("WARNING"), pytest.raises(
        PermanentMeetingRecordCallbackError
    ):
        client.send(
            meeting_id=MEETING_ID,
            project_id=PROJECT_ID,
            body={
                "commandId": str(COMMAND_ID),
                "title": "private title",
                "summary": [private_summary],
            },
        )

    assert api_key not in caplog.text
    assert private_summary not in caplog.text
    assert "INVALID_REQUEST" in caplog.text


def test_content_too_large_sends_one_deterministically_compacted_payload():
    requests: list[dict] = []
    body = build_callback_body(
        _result(
            structured={
                "summary": ["가" * 18_000],
                "decisions": [],
                "nextTodos": [],
                "issues": [],
            }
        ),
        command_id=COMMAND_ID,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                400,
                json={"errorCode": "MEETING_RECORD_CONTENT_TOO_LARGE"},
            )
        return httpx.Response(200, json=_success_response(duplicated=False))

    result = _callback_client(handler).send(
        meeting_id=MEETING_ID,
        body=body,
        project_id=PROJECT_ID,
    )

    assert result.duplicated is False
    assert len(requests) == 2
    assert requests[0] != requests[1]
    assert requests[1] == compact_callback_body(requests[0])
    assert requests[1]["commandId"] == requests[0]["commandId"]
    assert requests[1]["title"] == requests[0]["title"]
    for name in ("summary", "decisions", "nextTodos", "issues"):
        assert json_array_size_bytes(requests[1][name]) <= 50_000


def test_content_too_large_cannot_compact_empty_sections_and_does_not_resend():
    calls = 0
    body = build_callback_body(
        _result(
            structured={
                "summary": [],
                "decisions": [],
                "nextTodos": [],
                "issues": [],
            }
        ),
        command_id=COMMAND_ID,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            json={"errorCode": "MEETING_RECORD_CONTENT_TOO_LARGE"},
        )

    with pytest.raises(PermanentMeetingRecordCallbackError):
        _callback_client(handler).send(meeting_id=MEETING_ID, body=body)
    assert calls == 1


def test_compacted_callback_server_failure_is_not_retried_again():
    calls = 0
    body = build_callback_body(
        _result(
            structured={
                "summary": ["가" * 18_000],
                "decisions": [],
                "nextTodos": [],
                "issues": [],
            }
        ),
        command_id=COMMAND_ID,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                400,
                json={"errorCode": "MEETING_RECORD_CONTENT_TOO_LARGE"},
            )
        return httpx.Response(503, json={"errorCode": "UNAVAILABLE"})

    with pytest.raises(RetryableMeetingRecordCallbackError) as captured:
        _callback_client(handler).send(meeting_id=MEETING_ID, body=body)
    assert captured.value.coordinator_retryable is False
    assert calls == 2


@pytest.mark.parametrize(
    "value",
    [
        None,
        [None],
        [""],
        ["   "],
        [3],
        ["- bullet"],
        ["* bullet"],
        ["• bullet"],
    ],
)
def test_summary_array_contract_rejects_invalid_items(value):
    with pytest.raises(MeetingSummaryContractError):
        normalize_summary_items(value, "summary")


def test_summary_contract_accepts_empty_arrays_and_title_200_only():
    accepted = normalize_generated_summary(
        GeneratedMeetingSummary(title="가" * 200)
    )
    assert accepted.summary == ()
    with pytest.raises(MeetingSummaryContractError, match="200"):
        normalize_generated_summary(GeneratedMeetingSummary(title="가" * 201))


def test_summary_contract_rejects_more_than_500_items():
    with pytest.raises(MeetingSummaryContractError, match="500"):
        normalize_summary_items(["item"] * 501, "summary")


def test_summary_section_size_is_checked_before_callback():
    with pytest.raises(MeetingSummaryContractError, match="too large"):
        normalize_summary_items(["가" * 20_000], "summary")


class _SequenceCallback:
    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[tuple[str, dict]] = []

    def send(self, *, meeting_id, body, project_id=None):
        self.calls.append((str(meeting_id), deepcopy(body)))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _seed_command_summary(session_factory) -> None:
    with session_factory() as session:
        session.add(
            Meeting(
                project_id=PROJECT_ID,
                external_meeting_id=MEETING_ID,
                status="COMPLETED",
            )
        )
        session.add(
            TranscriptSegment(
                project_id=PROJECT_ID,
                external_meeting_id=MEETING_ID,
                segment_id="s1",
                sequence_no=1,
                text="회의 내용을 정리한다.",
                normalized_text="회의 내용을 정리한다.",
            )
        )
        session.add(
            MeetingAnalysisCommand(
                command_id=COMMAND_ID,
                project_id=PROJECT_ID,
                meeting_id=MEETING_ID,
                room_name="project-3-meeting-35",
                generate_summary=True,
                generate_nodes=False,
                requested_at=datetime.now(timezone.utc),
                status="READY",
                payload_hash="b" * 64,
            )
        )
        session.add_all(
            [
                MeetingAnalysisTask(
                    command_id=COMMAND_ID,
                    task_type="SUMMARY",
                    status="READY",
                    attempt_count=0,
                    max_attempts=3,
                ),
                MeetingAnalysisTask(
                    command_id=COMMAND_ID,
                    task_type="NODES",
                    status="SKIPPED",
                    attempt_count=0,
                    max_attempts=3,
                ),
            ]
        )
        session.add(
            RecordingReadyEvent(
                project_id=PROJECT_ID,
                room_name="project-3-meeting-35",
                egress_id="egress-summary-callback",
                kind="MIXED",
                member_id=None,
                recording_bucket="recordings",
                object_key="meetings/summary.ogg",
                status="READY",
            )
        )
        session.commit()


def _summary_generator() -> FakeMeetingSummaryGenerator:
    return FakeMeetingSummaryGenerator(
        GeneratedMeetingSummary(
            title="회의 제목",
            summary=("핵심 논의를 정리했다.",),
            decisions=("Java Callback을 사용한다.",),
            next_todos=("E2E 테스트를 수행한다.",),
            issues=(),
        )
    )


def _coordinator(session_factory, generator, callback):
    return MeetingAnalysisCoordinator(
        session_factory=session_factory,
        transcript_loader=lambda command, recording: [
            {"segmentId": "s1", "text": "회의 내용을 정리한다."}
        ],
        summary_processor=summary_processor(
            session_factory=session_factory,
            generator=generator,
            callback_client=callback,
        ),
        nodes_processor=lambda command, recording, transcript: None,
    )


def test_summary_callback_success_precedes_task_success_and_emits_no_ready_event(
    session_factory,
):
    _seed_command_summary(session_factory)
    generator = _summary_generator()
    callback = _SequenceCallback(
        [CallbackResult(91, MEETING_ID, str(COMMAND_ID), 0, False)]
    )

    result = _coordinator(session_factory, generator, callback).run_once()

    assert result.succeeded == ("SUMMARY",)
    assert callback.calls[0][1]["commandId"] == str(COMMAND_ID)
    with session_factory() as session:
        assert session.query(MeetingSummary).count() == 1
        task = session.execute(
            select(MeetingAnalysisTask).where(
                MeetingAnalysisTask.task_type == "SUMMARY"
            )
        ).scalar_one()
        assert task.status == "SUCCEEDED"
        assert session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "MEETING_SUMMARY_READY"
            )
        ).scalars().all() == []


def test_callback_retry_reuses_stored_summary_without_regeneration(session_factory):
    _seed_command_summary(session_factory)
    generator = _summary_generator()
    callback = _SequenceCallback(
        [
            RetryableMeetingRecordCallbackError("temporary"),
            CallbackResult(91, MEETING_ID, str(COMMAND_ID), 0, True),
        ]
    )
    coordinator = _coordinator(session_factory, generator, callback)

    assert coordinator.run_once().retrying == ("SUMMARY",)
    assert coordinator.run_once().succeeded == ("SUMMARY",)

    assert len(generator.calls) == 1
    assert len(callback.calls) == 2
    assert callback.calls[0] == callback.calls[1]
    with session_factory() as session:
        assert session.query(MeetingSummary).count() == 1


@pytest.mark.parametrize(
    ("status", "error_code"),
    [
        (400, "INVALID_REQUEST"),
        (401, "MEETING_RECORD_CALLBACK_UNAUTHORIZED"),
        (404, "MEETING_NOT_FOUND"),
        (409, "MEETING_RECORD_COMMAND_MISMATCH"),
    ],
)
def test_permanent_callback_failure_is_terminal_and_emits_one_failure_event(
    session_factory,
    status,
    error_code,
):
    _seed_command_summary(session_factory)
    callback = _SequenceCallback(
        [
            PermanentMeetingRecordCallbackError(
                status_code=status,
                error_code=error_code,
                message="rejected",
            )
        ]
    )

    result = _coordinator(
        session_factory, _summary_generator(), callback
    ).run_once()

    assert result.failed == ("SUMMARY",)
    assert len(callback.calls) == 1
    with session_factory() as session:
        events = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "ANALYSIS_TASK_STATUS_CHANGED"
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].payload["payload"]["failureCode"] == (
            "SUMMARY_CALLBACK_REJECTED"
        )


def test_content_too_large_compaction_success_marks_task_succeeded_without_regeneration(
    session_factory,
):
    _seed_command_summary(session_factory)
    requests: list[dict] = []
    generator = FakeMeetingSummaryGenerator(
        GeneratedMeetingSummary(
            title="회의 제목",
            summary=("가" * 18_000,),
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            return httpx.Response(
                400,
                json={"errorCode": "MEETING_RECORD_CONTENT_TOO_LARGE"},
            )
        return httpx.Response(200, json=_success_response(duplicated=False))

    result = _coordinator(
        session_factory,
        generator,
        _callback_client(handler),
    ).run_once()

    assert result.succeeded == ("SUMMARY",)
    assert len(generator.calls) == 1
    assert len(requests) == 2
    assert requests[0] != requests[1]
    assert requests[0]["commandId"] == requests[1]["commandId"]
    with session_factory() as session:
        row = session.execute(select(MeetingSummary)).scalar_one()
        assert row.structured_summary["summary"] == ["가" * 18_000]


def test_content_too_large_compaction_failure_is_terminal_with_one_event(
    session_factory,
):
    _seed_command_summary(session_factory)
    requests: list[dict] = []
    generator = _summary_generator()

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            400,
            json={"errorCode": "MEETING_RECORD_CONTENT_TOO_LARGE"},
        )

    result = _coordinator(
        session_factory,
        generator,
        _callback_client(handler),
    ).run_once()

    assert result.failed == ("SUMMARY",)
    assert len(generator.calls) == 1
    assert len(requests) == 2
    with session_factory() as session:
        events = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "ANALYSIS_TASK_STATUS_CHANGED"
            )
        ).scalars().all()
        assert len(events) == 1


def test_already_failed_callback_marks_task_failed_without_duplicate_event(
    session_factory,
):
    _seed_command_summary(session_factory)
    callback = _SequenceCallback(
        [
            PermanentMeetingRecordCallbackError(
                status_code=409,
                error_code="MEETING_RECORD_SUMMARY_ALREADY_FAILED",
                message="already failed",
            )
        ]
    )

    result = _coordinator(
        session_factory, _summary_generator(), callback
    ).run_once()

    assert result.failed == ("SUMMARY",)
    with session_factory() as session:
        assert session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "ANALYSIS_TASK_STATUS_CHANGED"
            )
        ).scalars().all() == []


def test_delivery_failure_exhaustion_emits_exactly_one_failure_event(
    session_factory,
):
    _seed_command_summary(session_factory)
    generator = _summary_generator()
    callback = _SequenceCallback(
        [
            RetryableMeetingRecordCallbackError("network unavailable"),
            RetryableMeetingRecordCallbackError("network unavailable"),
            RetryableMeetingRecordCallbackError("network unavailable"),
        ]
    )
    coordinator = _coordinator(session_factory, generator, callback)

    assert coordinator.run_once().retrying == ("SUMMARY",)
    assert coordinator.run_once().retrying == ("SUMMARY",)
    assert coordinator.run_once().failed == ("SUMMARY",)

    assert len(generator.calls) == 1
    with session_factory() as session:
        events = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "ANALYSIS_TASK_STATUS_CHANGED"
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].payload["payload"]["failureCode"] == (
            "SUMMARY_CALLBACK_DELIVERY_FAILED"
        )


def test_generation_failure_exhaustion_emits_exactly_one_failure_event(
    session_factory,
):
    _seed_command_summary(session_factory)
    generator = FakeMeetingSummaryGenerator(
        GeneratedMeetingSummary(title=" ")
    )
    callback = _SequenceCallback([])
    coordinator = _coordinator(session_factory, generator, callback)

    assert coordinator.run_once().retrying == ("SUMMARY",)
    assert coordinator.run_once().retrying == ("SUMMARY",)
    assert coordinator.run_once().failed == ("SUMMARY",)

    assert len(generator.calls) == 3
    assert callback.calls == []
    with session_factory() as session:
        events = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "ANALYSIS_TASK_STATUS_CHANGED"
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].payload["payload"]["failureCode"] == (
            "SUMMARY_GENERATION_FAILED"
        )


def test_failure_event_normalizes_required_length_limits(session_factory):
    _seed_command_summary(session_factory)
    with session_factory() as session:
        command = session.execute(select(MeetingAnalysisCommand)).scalar_one()
        event = stage_task_failed_v3(
            session,
            command=command,
            task_type="NODES",
            failure_code="C" * 150,
            failure_message="M" * 1500,
        )
        session.commit()
        payload = event.payload["payload"]
        assert payload["failureCode"] == "C" * 100
        assert payload["failureMessage"] == "M" * 1000

    with session_factory() as session, pytest.raises(
        ValueError, match="must not be blank"
    ):
        command = session.execute(select(MeetingAnalysisCommand)).scalar_one()
        stage_task_failed_v3(
            session,
            command=command,
            task_type="SUMMARY",
            failure_code="   ",
        )


def test_coordinator_runtime_fails_before_aws_when_callback_env_is_missing(
    monkeypatch,
):
    from data_pipeline.meeting_analysis import runtime

    monkeypatch.setenv("JAVA_BASE_URL", "")
    monkeypatch.setenv("MEETING_RECORD_CALLBACK_API_KEY", "")
    monkeypatch.setenv("MEETING_RECORD_CALLBACK_TIMEOUT_SECONDS", "10")
    aws_called = False

    def fail_if_called(region):
        nonlocal aws_called
        aws_called = True
        raise AssertionError("AWS clients must not be built")

    monkeypatch.setattr(runtime, "_aws_clients", fail_if_called)
    with pytest.raises(ValueError, match="JAVA_BASE_URL"):
        runtime.build_coordinator_runtime()
    assert aws_called is False


@pytest.mark.parametrize(
    ("base_url", "api_key", "timeout", "message"),
    [
        ("https://java.example", "", "10", "API_KEY"),
        ("https://java.example", "secret", "0", "positive"),
        ("https://java.example", "secret", "nan", "positive"),
        ("https://java.example", "secret", "invalid", "number"),
    ],
)
def test_callback_environment_validation(
    monkeypatch,
    base_url,
    api_key,
    timeout,
    message,
):
    monkeypatch.setenv("JAVA_BASE_URL", base_url)
    monkeypatch.setenv("MEETING_RECORD_CALLBACK_API_KEY", api_key)
    monkeypatch.setenv("MEETING_RECORD_CALLBACK_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValueError, match=message):
        load_meeting_record_callback_settings()
