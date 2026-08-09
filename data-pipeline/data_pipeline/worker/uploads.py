"""Transactional claim/finalization service for S3 upload events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from data_pipeline.storage import AudioUploadEvent

from .errors import UploadAlreadyProcessing
from .s3_events import S3ObjectRecord


@dataclass(frozen=True)
class UploadClaim:
    outcome: str
    event_id: uuid.UUID
    claim_token: uuid.UUID | None
    attempt: int

    @property
    def claimed(self) -> bool:
        return self.outcome == "CLAIMED"

    @property
    def completed(self) -> bool:
        return self.outcome == "ALREADY_COMPLETED"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _event_query(record: S3ObjectRecord):
    return select(AudioUploadEvent).where(
        AudioUploadEvent.bucket == record.bucket,
        AudioUploadEvent.object_key == record.object_key,
        AudioUploadEvent.object_identity == record.object_identity,
    )


def _existing_claim(
    row: AudioUploadEvent,
    *,
    stale_after: timedelta,
    now: datetime,
) -> UploadClaim | None:
    if row.status == "COMPLETED":
        return UploadClaim("ALREADY_COMPLETED", row.id, None, row.attempt_count)
    if (
        row.status == "PROCESSING"
        and _as_utc(row.processing_started_at) > now - stale_after
    ):
        return UploadClaim("IN_PROGRESS", row.id, None, row.attempt_count)
    return None


def claim_upload_event(
    session_factory: sessionmaker,
    *,
    record: S3ObjectRecord,
    stale_after: timedelta,
) -> UploadClaim:
    if stale_after.total_seconds() <= 0:
        raise ValueError("stale_after must be positive")
    now = _now()
    session = session_factory()
    try:
        row = session.execute(
            _event_query(record).with_for_update()
        ).scalar_one_or_none()
        if row is not None:
            existing = _existing_claim(row, stale_after=stale_after, now=now)
            if existing is not None:
                session.rollback()
                return existing
            token = uuid.uuid4()
            row.status = "PROCESSING"
            row.attempt_count += 1
            row.claim_token = token
            row.processing_started_at = now
            row.failed_at = None
            row.failure_code = None
            row.failure_message = None
            row.updated_at = now
            session.commit()
            return UploadClaim("CLAIMED", row.id, token, row.attempt_count)

        token = uuid.uuid4()
        row = AudioUploadEvent(
            bucket=record.bucket,
            object_key=record.object_key,
            object_identity=record.object_identity,
            identity_kind=record.identity_kind,
            version_id=record.version_id,
            etag=record.etag,
            object_size=record.size,
            project_id=record.project_id,
            external_meeting_id=record.external_meeting_id,
            upload_id=record.upload_id,
            filename=record.filename,
            status="PROCESSING",
            attempt_count=1,
            claim_token=token,
            processing_started_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
            winner = session.execute(
                _event_query(record).with_for_update()
            ).scalar_one()
            existing = _existing_claim(
                winner,
                stale_after=stale_after,
                now=now,
            )
            if existing is not None:
                return existing
            token = uuid.uuid4()
            winner.status = "PROCESSING"
            winner.attempt_count += 1
            winner.claim_token = token
            winner.processing_started_at = now
            winner.failed_at = None
            winner.failure_code = None
            winner.failure_message = None
            winner.updated_at = now
            session.commit()
            return UploadClaim(
                "CLAIMED",
                winner.id,
                token,
                winner.attempt_count,
            )
        return UploadClaim("CLAIMED", row.id, token, 1)
    finally:
        session.close()


def complete_upload_event(
    session_factory: sessionmaker,
    *,
    claim: UploadClaim,
    external_request_id: str,
    pipeline_status: str,
    pipeline_outcome: str,
) -> None:
    if claim.claim_token is None:
        raise ValueError("A claimed upload is required")
    session = session_factory()
    try:
        row = session.execute(
            select(AudioUploadEvent)
            .where(
                AudioUploadEvent.id == claim.event_id,
                AudioUploadEvent.claim_token == claim.claim_token,
                AudioUploadEvent.status == "PROCESSING",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            raise UploadAlreadyProcessing("Upload claim is no longer current")
        now = _now()
        row.status = "COMPLETED"
        row.external_request_id = external_request_id
        row.pipeline_status = pipeline_status
        row.pipeline_outcome = pipeline_outcome
        row.completed_at = now
        row.claim_token = None
        row.failure_code = None
        row.failure_message = None
        row.updated_at = now
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def fail_upload_event(
    session_factory: sessionmaker,
    *,
    claim: UploadClaim,
    error: Exception,
) -> bool:
    if claim.claim_token is None:
        return False
    session = session_factory()
    try:
        row = session.execute(
            select(AudioUploadEvent)
            .where(
                AudioUploadEvent.id == claim.event_id,
                AudioUploadEvent.claim_token == claim.claim_token,
                AudioUploadEvent.status == "PROCESSING",
            )
            .with_for_update()
        ).scalar_one_or_none()
        if row is None:
            session.rollback()
            return False
        now = _now()
        row.status = "FAILED"
        row.failure_code = type(error).__name__[:128]
        row.failure_message = str(error)[:2000]
        row.failed_at = now
        row.claim_token = None
        row.updated_at = now
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "UploadClaim",
    "claim_upload_event",
    "complete_upload_event",
    "fail_upload_event",
]
