"""Enqueue and claim durable analysis jobs.

The HTTP layer only ever enqueues; all embedding, Retrieval and B-model work
happens in the Analysis Worker so no user request and no SQS message is held
open while a person reviews.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from data_pipeline.storage import AnalysisJob, Node

from .claiming import as_utc, backoff_delay, claim_rows, utcnow

PENDING = "PENDING"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"

#: A RUNNING row whose worker died is reclaimed after this long.
DEFAULT_CLAIM_TIMEOUT_SECONDS = 1800


@dataclass(frozen=True)
class ClaimedAnalysisJob:
    job_id: uuid.UUID
    project_id: str
    external_meeting_id: str
    node_id: uuid.UUID
    node_version: int
    attempt: int
    claim_token: uuid.UUID


def enqueue_analysis_job(
    session,
    *,
    project_id: str,
    external_meeting_id: str,
    node_id: uuid.UUID,
    node_version: int,
    max_attempts: int = 3,
) -> AnalysisJob:
    """Add or revive the single job row for one Node.

    Must be called inside the caller's transaction so the job is committed
    atomically with the Node it analyses.
    """

    node_exists = session.execute(
        select(Node.id).where(
            Node.id == node_id,
            Node.project_id == project_id,
        )
    ).scalar_one_or_none()
    if node_exists is None:
        raise ValueError(
            "analysis job Node does not exist in the requested project"
        )

    existing = session.execute(
        select(AnalysisJob).where(
            AnalysisJob.node_id == node_id,
            AnalysisJob.project_id == project_id,
        )
    ).scalar_one_or_none()
    now = utcnow()
    if existing is not None:
        # A newer Node version invalidates a finished job; re-queue it.
        existing.status = PENDING
        existing.node_version = node_version
        existing.attempt_count = 0
        existing.claim_token = None
        existing.claimed_at = None
        existing.available_at = now
        existing.failure_code = None
        existing.last_error = None
        existing.updated_at = now
        return existing

    job = AnalysisJob(
        project_id=project_id,
        external_meeting_id=external_meeting_id,
        node_id=node_id,
        node_version=node_version,
        status=PENDING,
        attempt_count=0,
        max_attempts=max_attempts,
        available_at=now,
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    # Flush so a duplicate node_id surfaces here as an IntegrityError. It is
    # deliberately NOT caught: this runs inside the caller's transaction, so
    # rolling back here would silently discard everything the caller staged.
    session.flush()
    return job


def claim_next_analysis_job(
    session_factory,
    *,
    claim_timeout_seconds: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
) -> ClaimedAnalysisJob | None:
    """Take ownership of one claimable job, or return None when idle."""

    session = session_factory()
    try:
        now = utcnow()
        # A RUNNING row claimed more recently than this is still owned by a live
        # worker; anything older is assumed abandoned and may be reclaimed.
        stale_before = now - timedelta(seconds=claim_timeout_seconds)
        statement = (
            select(AnalysisJob)
            .where(
                AnalysisJob.status.in_((PENDING, RUNNING)),
                AnalysisJob.available_at <= now,
            )
            .order_by(AnalysisJob.available_at, AnalysisJob.created_at)
        )
        for job in claim_rows(session, statement, limit=10):
            if job.status == RUNNING:
                claimed_at = as_utc(job.claimed_at)
                if claimed_at is not None and claimed_at > stale_before:
                    continue  # still owned by a live worker
            token = uuid.uuid4()
            job.status = RUNNING
            job.attempt_count += 1
            job.claim_token = token
            job.claimed_at = now
            # Push the claim past the timeout so this RUNNING row leaves the
            # `available_at <= now` window. Without this, in-flight rows keep
            # their original (older) available_at, sort ahead of new PENDING
            # work and fill the limit, starving the queue until they finish.
            job.available_at = now + timedelta(seconds=claim_timeout_seconds)
            job.updated_at = now
            claimed = ClaimedAnalysisJob(
                job_id=job.id,
                project_id=job.project_id,
                external_meeting_id=job.external_meeting_id,
                node_id=job.node_id,
                node_version=job.node_version,
                attempt=job.attempt_count,
                claim_token=token,
            )
            session.commit()
            return claimed
        session.rollback()
        return None
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def complete_analysis_job(
    session_factory,
    *,
    job_id: uuid.UUID,
    claim_token: uuid.UUID,
    analysis_run_id: uuid.UUID | None,
    on_session=None,
) -> bool:
    """Mark the job SUCCEEDED.

    ``on_session`` is invoked with the open session before the commit so the
    caller can stage an outbox event in the SAME transaction. Emitting after
    this function returns would let the status change commit while the
    notification is lost, which is exactly what the outbox exists to prevent.
    """

    session = session_factory()
    try:
        job = _owned(session, job_id, claim_token)
        if job is None:
            session.rollback()
            return False
        now = utcnow()
        job.status = SUCCEEDED
        job.analysis_run_id = analysis_run_id
        job.claim_token = None
        job.failure_code = None
        job.last_error = None
        job.updated_at = now
        if on_session is not None:
            on_session(session)
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def fail_analysis_job(
    session_factory,
    *,
    job_id: uuid.UUID,
    claim_token: uuid.UUID,
    failure_code: str,
    error: str,
    retryable: bool = True,
    on_terminal_failure=None,
) -> str:
    """Record a failure. Returns the resulting status (PENDING or FAILED).

    ``on_terminal_failure`` is invoked with the open session before the commit,
    and only when the job becomes terminally FAILED, so a PIPELINE_FAILED event
    commits atomically with the status that triggered it.
    """

    session = session_factory()
    try:
        job = _owned(session, job_id, claim_token)
        if job is None:
            session.rollback()
            return "UNOWNED"
        now = utcnow()
        job.claim_token = None
        job.failure_code = failure_code[:128]
        job.last_error = error[:2000]
        job.updated_at = now
        if retryable and job.attempt_count < job.max_attempts:
            job.status = PENDING
            job.available_at = now + backoff_delay(job.attempt_count)
        else:
            job.status = FAILED
            if on_terminal_failure is not None:
                on_terminal_failure(session)
        result = job.status
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _owned(session, job_id: uuid.UUID, claim_token: uuid.UUID) -> AnalysisJob | None:
    return session.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.id == job_id,
            AnalysisJob.claim_token == claim_token,
            AnalysisJob.status == RUNNING,
        )
        .with_for_update()
    ).scalar_one_or_none()


__all__ = [
    "FAILED",
    "PENDING",
    "RUNNING",
    "SUCCEEDED",
    "ClaimedAnalysisJob",
    "claim_next_analysis_job",
    "complete_analysis_job",
    "enqueue_analysis_job",
    "fail_analysis_job",
]
