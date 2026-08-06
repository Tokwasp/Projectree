from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from data_pipeline.api.app import create_app
from data_pipeline.api.dependencies import get_session_factory
from data_pipeline.meeting_summary import (
    FakeMeetingSummaryGenerator,
    GmsMeetingSummaryGenerator,
    GeneratedMeetingSummary,
    MeetingSummaryConflictError,
    MeetingSummaryInput,
    MeetingSummaryResponseError,
    SummarySegment,
    build_meeting_summary_generator,
    generate_meeting_summary,
)
from data_pipeline.llm import LLMResponse
from data_pipeline.provider_safety import ExternalAIProviderBlockedError
from data_pipeline.pipeline.event_contract import (
    mark_graph_ready,
    stage_analysis_failed,
    stage_analysis_processing,
)
from data_pipeline.storage import Meeting, MeetingSummary, OutboxEvent, TranscriptSegment

PROJECT = "summary-project"
MEETING = "summary-meeting"
FIXTURE = Path(__file__).parent / "fixtures" / "meeting_summary" / "golden_summary.json"


def _seed_transcript(session_factory) -> None:
    with session_factory() as session:
        session.add(
            Meeting(
                project_id=PROJECT,
                external_meeting_id=MEETING,
                status="COMPLETED",
            )
        )
        session.add_all(
            [
                TranscriptSegment(
                    project_id=PROJECT,
                    external_meeting_id=MEETING,
                    segment_id="s1",
                    sequence_no=1,
                    speaker_label="민수",
                    text="포스트그레스큐엘을 정본으로 유지합니다.",
                    normalized_text="PostgreSQL을 정본으로 유지합니다.",
                ),
                TranscriptSegment(
                    project_id=PROJECT,
                    external_meeting_id=MEETING,
                    segment_id="s2",
                    sequence_no=2,
                    speaker_label="지수",
                    text="패스트 에이피아이 계약을 전달할게요.",
                    normalized_text="FastAPI 계약을 전달할게요.",
                ),
            ]
        )
        session.commit()


def _generator() -> FakeMeetingSummaryGenerator:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return FakeMeetingSummaryGenerator(
        GeneratedMeetingSummary(
            title=payload["title"],
            summary=tuple(payload["summary"]),
            decisions=tuple(payload["decisions"]),
            next_todos=tuple(payload["nextTodos"]),
            issues=tuple(payload["issues"]),
        )
    )


class _SummaryChatClient:
    def __init__(self, raw_response: str) -> None:
        self.raw_response = raw_response
        self.messages: list[list[dict[str, str]]] = []

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        self.messages.append(messages)
        return LLMResponse(
            raw_response=self.raw_response,
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            latency_ms=1,
        )


def _summary_input() -> MeetingSummaryInput:
    return MeetingSummaryInput(
        project_id=PROJECT,
        external_meeting_id=MEETING,
        segments=(
            SummarySegment(
                segment_id="s1",
                sequence_no=1,
                speaker_label="Backend",
                text="PostgreSQL을 그래프 원본으로 사용하기로 결정했습니다.",
            ),
        ),
    )


def test_gms_summary_adapter_parses_strict_grounded_document_without_network():
    client = _SummaryChatClient(
        json.dumps(
            {
                "title": "그래프 저장소 회의",
                "summary": ["그래프 저장소 운영 방식을 논의했다."],
                "decisions": ["PostgreSQL을 그래프 원본으로 사용한다."],
                "nextTodos": [],
                "issues": [],
            },
            ensure_ascii=False,
        )
    )
    generator = GmsMeetingSummaryGenerator(client)

    result = generator.generate(_summary_input())

    assert result.title == "그래프 저장소 회의"
    assert result.decisions == ("PostgreSQL을 그래프 원본으로 사용한다.",)
    assert generator.version == "meeting-summary-v2"
    system_prompt = client.messages[0][0]["content"]
    for key in ("title", "summary", "decisions", "nextTodos", "issues"):
        assert key in system_prompt
    assert "200자 이하" in system_prompt
    assert "null을 반환하지 않는다" in system_prompt
    request_payload = json.loads(client.messages[0][1]["content"])
    assert request_payload["transcript"][0]["text"].startswith("PostgreSQL")


@pytest.mark.parametrize(
    "raw_response",
    [
        "not-json",
        json.dumps({"title": "missing fields"}),
        json.dumps(
            {
                "title": "legacy body",
                "body": "본문",
                "decisions": [],
                "actions": [],
                "issues": [],
            }
        ),
        json.dumps(
            {
                "title": "title",
                "summary": [],
                "decisions": "not-an-array",
                "nextTodos": [],
                "issues": [],
            }
        ),
    ],
)
def test_gms_summary_adapter_rejects_invalid_provider_contract(raw_response):
    with pytest.raises(MeetingSummaryResponseError):
        GmsMeetingSummaryGenerator(_SummaryChatClient(raw_response)).generate(
            _summary_input()
        )


@pytest.mark.parametrize("title_length", [200, 201])
def test_gms_summary_title_boundary(title_length: int):
    raw = json.dumps(
        {
            "title": "가" * title_length,
            "summary": [],
            "decisions": [],
            "nextTodos": [],
            "issues": [],
        },
        ensure_ascii=False,
    )
    generator = GmsMeetingSummaryGenerator(_SummaryChatClient(raw))

    if title_length == 200:
        assert len(generator.generate(_summary_input()).title) == 200
    else:
        with pytest.raises(MeetingSummaryResponseError):
            generator.generate(_summary_input())


def test_summary_factory_rejects_fake_in_production_and_accepts_injected_gms():
    with pytest.raises(RuntimeError, match="forbidden"):
        build_meeting_summary_generator("fake", app_env="production")

    client = _SummaryChatClient(
        json.dumps(
            {
                "title": "title",
                "summary": [],
                "decisions": [],
                "nextTodos": [],
                "issues": [],
            }
        )
    )
    generator = build_meeting_summary_generator(
        "gms",
        app_env="production",
        chat_client=client,
    )
    assert isinstance(generator, GmsMeetingSummaryGenerator)


def test_fake_summary_persistence_outbox_and_idempotent_replay(session_factory):
    _seed_transcript(session_factory)
    generator = _generator()

    created = generate_meeting_summary(
        session_factory,
        project_id=PROJECT,
        external_meeting_id=MEETING,
        summary_version=1,
        generator=generator,
    )
    replayed = generate_meeting_summary(
        session_factory,
        project_id=PROJECT,
        external_meeting_id=MEETING,
        summary_version=1,
        generator=generator,
    )

    assert created.body == "\n".join(
        json.loads(FIXTURE.read_text(encoding="utf-8"))["summary"]
    )
    assert replayed.summary_id == created.summary_id
    assert replayed.replayed is True
    assert len(generator.calls) == 1
    assert [segment.text for segment in generator.calls[0].segments] == [
        "PostgreSQL을 정본으로 유지합니다.",
        "FastAPI 계약을 전달할게요.",
    ]
    with session_factory() as session:
        assert session.query(MeetingSummary).count() == 1
        events = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "MEETING_SUMMARY_READY"
            )
        ).scalars().all()
        assert len(events) == 1
        assert events[0].payload == {
            "meetingSummaryId": str(created.summary_id),
            "projectId": PROJECT,
            "externalMeetingId": MEETING,
            "summaryVersion": 1,
            "status": "READY",
            "apiPath": f"/api/v1/meetings/{MEETING}/summary?summaryVersion=1",
        }


def test_summary_version_refuses_different_transcript_input(session_factory):
    _seed_transcript(session_factory)
    generator = _generator()
    generate_meeting_summary(
        session_factory,
        project_id=PROJECT,
        external_meeting_id=MEETING,
        summary_version=1,
        generator=generator,
    )
    with session_factory() as session:
        segment = session.execute(
            select(TranscriptSegment).where(TranscriptSegment.segment_id == "s1")
        ).scalar_one()
        segment.normalized_text = "변경된 정규화문"
        session.commit()

    with pytest.raises(MeetingSummaryConflictError):
        generate_meeting_summary(
            session_factory,
            project_id=PROJECT,
            external_meeting_id=MEETING,
            summary_version=1,
            generator=generator,
        )
    assert len(generator.calls) == 1


def test_summary_api_returns_latest_version_and_hides_other_project(
    session_factory,
):
    _seed_transcript(session_factory)
    created = generate_meeting_summary(
        session_factory,
        project_id=PROJECT,
        external_meeting_id=MEETING,
        summary_version=1,
        generator=_generator(),
    )
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    with TestClient(app) as client:
        response = client.get(
            f"/api/v1/meetings/{MEETING}/summary",
            headers={"X-Project-Id": PROJECT},
        )
        hidden = client.get(
            f"/api/v1/meetings/{MEETING}/summary",
            headers={"X-Project-Id": "other-project"},
        )
    app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["meetingSummaryId"] == str(created.summary_id)
    assert response.json()["decisions"] == [
        "PostgreSQL을 그래프 정본으로 유지한다."
    ]
    assert hidden.status_code == 404


def test_external_ai_client_guard_is_active():
    from data_pipeline.provider_safety import assert_external_ai_client_allowed

    with pytest.raises(ExternalAIProviderBlockedError):
        assert_external_ai_client_allowed("contract-test")


def test_analysis_succeeds_only_after_graph_and_summary_are_ready(session_factory):
    _seed_transcript(session_factory)
    with session_factory() as session:
        stage_analysis_processing(
            session,
            project_id=PROJECT,
            external_meeting_id=MEETING,
        )
        mark_graph_ready(
            session,
            project_id=PROJECT,
            external_meeting_id=MEETING,
            graph_version=9,
        )
        session.commit()

    with session_factory() as session:
        statuses = [
            row.payload["status"]
            for row in session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.event_type == "ANALYSIS_STATUS_CHANGED")
                .order_by(OutboxEvent.created_at)
            ).scalars()
        ]
        assert statuses == ["PROCESSING"]

    generate_meeting_summary(
        session_factory,
        project_id=PROJECT,
        external_meeting_id=MEETING,
        summary_version=1,
        generator=_generator(),
    )
    with session_factory() as session:
        events = list(
            session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.event_type == "ANALYSIS_STATUS_CHANGED")
                .order_by(OutboxEvent.created_at)
            ).scalars()
        )
        assert [row.payload["status"] for row in events] == [
            "PROCESSING",
            "SUCCEEDED",
        ]
        assert events[-1].payload["requiredGraphVersion"] == 9
        assert events[-1].payload["requiredSummaryVersion"] == 1


def test_analysis_failed_event_contains_only_sanitized_operational_message(
    session_factory,
):
    with session_factory() as session:
        stage_analysis_processing(
            session,
            project_id=PROJECT,
            external_meeting_id=MEETING,
        )
        stage_analysis_failed(
            session,
            project_id=PROJECT,
            external_meeting_id=MEETING,
            failure_code="GRAPH_VALIDATION_FAILED",
            failure_message="GraphIntegrityError",
        )
        session.commit()
    with session_factory() as session:
        event = session.execute(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "ANALYSIS_STATUS_CHANGED",
                OutboxEvent.payload["status"].as_string() == "FAILED",
            )
        ).scalar_one()
        assert event.payload["failureCode"] == "GRAPH_VALIDATION_FAILED"
        assert event.payload["failureMessage"] == "GraphIntegrityError"
