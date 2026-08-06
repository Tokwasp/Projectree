"""Generate and persist immutable meeting summaries transactionally."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from data_pipeline.pipeline.event_contract import mark_summary_ready, stage_meeting_summary_ready
from data_pipeline.storage import (
    Meeting,
    MeetingAnalysisCommand,
    MeetingSummary,
    TranscriptSegment,
)
from .contracts import (
    GeneratedMeetingSummary,
    MeetingSummaryContractError,
    MeetingSummaryGenerator,
    MeetingSummaryInput,
    SummarySegment,
    normalize_generated_summary,
)


class MeetingSummaryNotFoundError(LookupError):
    pass


class MeetingSummarySourceError(ValueError):
    pass


class MeetingSummaryConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class MeetingSummaryResult:
    summary_id: uuid.UUID
    project_id: str
    external_meeting_id: str
    summary_version: int
    source_hash: str
    title: str
    body: str
    structured_summary: dict
    status: str
    generator_name: str
    generator_version: str
    created_at: datetime
    replayed: bool = False


def _result(row: MeetingSummary, *, replayed: bool = False) -> MeetingSummaryResult:
    return MeetingSummaryResult(
        summary_id=row.id,
        project_id=row.project_id,
        external_meeting_id=row.external_meeting_id,
        summary_version=row.summary_version,
        source_hash=row.source_hash,
        title=row.title,
        body=row.body,
        structured_summary=dict(row.structured_summary or {}),
        status=row.status,
        generator_name=row.generator_name,
        generator_version=row.generator_version,
        created_at=row.created_at,
        replayed=replayed,
    )


def _load_input(
    session_factory,
    *,
    project_id: str,
    external_meeting_id: str,
) -> MeetingSummaryInput:
    with session_factory() as session:
        meeting = session.execute(
            select(Meeting).where(
                Meeting.project_id == project_id,
                Meeting.external_meeting_id == external_meeting_id,
            )
        ).scalar_one_or_none()
        if meeting is None:
            raise MeetingSummaryNotFoundError("meeting not found")
        rows = session.execute(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.project_id == project_id,
                TranscriptSegment.external_meeting_id == external_meeting_id,
            )
            .order_by(TranscriptSegment.sequence_no, TranscriptSegment.segment_id)
        ).scalars().all()
    return MeetingSummaryInput(
        project_id=project_id,
        external_meeting_id=external_meeting_id,
        segments=tuple(
            SummarySegment(
                segment_id=row.segment_id,
                sequence_no=row.sequence_no,
                speaker_label=row.speaker_label,
                text=(row.normalized_text or row.text).strip(),
            )
            for row in rows
        ),
    )


def _source_hash(request: MeetingSummaryInput) -> str:
    payload = [
        {
            "segmentId": segment.segment_id,
            "sequenceNo": segment.sequence_no,
            "speakerLabel": segment.speaker_label,
            "text": segment.text,
        }
        for segment in request.segments
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _existing(
    session,
    *,
    project_id: str,
    external_meeting_id: str,
    summary_version: int,
) -> MeetingSummary | None:
    return session.execute(
        select(MeetingSummary).where(
            MeetingSummary.project_id == project_id,
            MeetingSummary.external_meeting_id == external_meeting_id,
            MeetingSummary.summary_version == summary_version,
        )
    ).scalar_one_or_none()


def _analysis_command(session, *, project_id: str, meeting_id: str):
    return session.execute(
        select(MeetingAnalysisCommand).where(
            MeetingAnalysisCommand.project_id == project_id,
            MeetingAnalysisCommand.meeting_id == meeting_id,
        )
    ).scalar_one_or_none()


def generate_meeting_summary(
    session_factory,
    *,
    project_id: str,
    external_meeting_id: str,
    summary_version: int,
    generator: MeetingSummaryGenerator,
) -> MeetingSummaryResult:
    """Generate once and persist immutable minutes before Java delivery."""

    if summary_version < 1:
        raise MeetingSummarySourceError("summary_version must be positive")
    request = _load_input(
        session_factory,
        project_id=project_id,
        external_meeting_id=external_meeting_id,
    )
    source_hash = _source_hash(request)

    with session_factory() as session:
        existing = _existing(
            session,
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            summary_version=summary_version,
        )
        if existing is not None:
            if existing.source_hash != source_hash:
                raise MeetingSummaryConflictError(
                    "summary_version already belongs to different transcript input"
                )
            command = _analysis_command(
                session,
                project_id=project_id,
                meeting_id=external_meeting_id,
            )
            if command is None:
                mark_summary_ready(session, summary=existing)
                session.commit()
            return _result(existing, replayed=True)

    try:
        document = normalize_generated_summary(generator.generate(request))
    except MeetingSummaryContractError as exc:
        raise MeetingSummarySourceError(str(exc)) from exc
    session = session_factory()
    try:
        row = MeetingSummary(
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            summary_version=summary_version,
            source_hash=source_hash,
            title=document.title,
            body="\n".join(document.summary),
            structured_summary=document.structured(),
            status="READY",
            generator_name=generator.name,
            generator_version=generator.version,
        )
        session.add(row)
        session.flush()
        api_path = (
            "/api/v1/meetings/"
            f"{quote(external_meeting_id, safe='')}/summary"
            f"?summaryVersion={summary_version}"
        )
        command = _analysis_command(
            session,
            project_id=project_id,
            meeting_id=external_meeting_id,
        )
        if command is None:
            stage_meeting_summary_ready(
                session,
                summary=row,
                api_path=api_path,
            )
        # Command-based SUMMARY success is delivered by the Java HTTP
        # callback. Only the legacy no-command path keeps its historical event.
        session.commit()
        return _result(row)
    except IntegrityError:
        session.rollback()
        winner = _existing(
            session,
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            summary_version=summary_version,
        )
        if winner is not None and winner.source_hash == source_hash:
            command = _analysis_command(
                session,
                project_id=project_id,
                meeting_id=external_meeting_id,
            )
            if command is None:
                mark_summary_ready(session, summary=winner)
                session.commit()
            return _result(winner, replayed=True)
        raise MeetingSummaryConflictError(
            "summary_version was concurrently claimed by different input"
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_meeting_summary(
    session_factory,
    *,
    project_id: str,
    external_meeting_id: str,
    summary_version: int | None = None,
) -> MeetingSummaryResult:
    with session_factory() as session:
        statement = select(MeetingSummary).where(
            MeetingSummary.project_id == project_id,
            MeetingSummary.external_meeting_id == external_meeting_id,
        )
        if summary_version is not None:
            statement = statement.where(
                MeetingSummary.summary_version == summary_version
            )
        row = session.execute(
            statement.order_by(MeetingSummary.summary_version.desc()).limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise MeetingSummaryNotFoundError("meeting summary not found")
        return _result(row)


__all__ = [
    "MeetingSummaryConflictError",
    "MeetingSummaryNotFoundError",
    "MeetingSummaryResult",
    "MeetingSummarySourceError",
    "generate_meeting_summary",
    "get_meeting_summary",
]
