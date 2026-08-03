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
    GeneratedMeetingSummary,
    MeetingSummaryConflictError,
    generate_meeting_summary,
)
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
            body=payload["body"],
            decisions=tuple(payload["decisions"]),
            actions=tuple(payload["actions"]),
            issues=tuple(payload["issues"]),
        )
    )


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

    assert created.body == json.loads(FIXTURE.read_text(encoding="utf-8"))["body"]
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
