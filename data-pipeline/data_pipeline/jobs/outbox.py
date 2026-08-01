"""Transactional outbox: emission helper, transport port, and relay.

The outbox does not replace the queue. It exists so a domain state change and
the notification about it either both commit or neither does. Delivery is
**at-least-once**: the relay may publish an event twice (for example when the
transport succeeds but the status write is lost), so consumers must deduplicate
on ``eventId``. This is deliberately not exactly-once.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy import select

from data_pipeline.storage import OutboxEvent

from .claiming import backoff_delay, claim_rows, utcnow

logger = logging.getLogger(__name__)

PENDING = "PENDING"
PUBLISHING = "PUBLISHING"
PUBLISHED = "PUBLISHED"
DEAD = "DEAD"

# --- event types this pipeline emits -----------------------------------------
INITIAL_REVIEW_READY = "INITIAL_REVIEW_READY"
ANALYSIS_QUEUED = "ANALYSIS_QUEUED"
FINAL_REVIEW_READY = "FINAL_REVIEW_READY"
PIPELINE_COMPLETED = "PIPELINE_COMPLETED"
PIPELINE_FAILED = "PIPELINE_FAILED"

PIPELINE_EVENT_TYPES = frozenset(
    {
        INITIAL_REVIEW_READY,
        ANALYSIS_QUEUED,
        FINAL_REVIEW_READY,
        PIPELINE_COMPLETED,
        PIPELINE_FAILED,
    }
)

SCHEMA_VERSION = "v2.2"


@dataclass(frozen=True)
class OutboxMessage:
    """One envelope handed to a transport."""

    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    project_id: str
    schema_version: str
    occurred_at: datetime
    payload: dict

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, default=str)

    def as_dict(self) -> dict:
        return {
            "eventId": self.event_id,
            "eventType": self.event_type,
            "aggregateType": self.aggregate_type,
            "aggregateId": self.aggregate_id,
            "projectId": self.project_id,
            "schemaVersion": self.schema_version,
            "occurredAt": self.occurred_at.isoformat(),
            "payload": self.payload,
        }


class OutboxTransport(Protocol):
    def publish(self, message: OutboxMessage) -> None: ...


class FakeOutboxTransport:
    """Records deliveries; used by tests and by a dry-run publisher."""

    def __init__(self, *, fail_times: int = 0, fail_forever: bool = False):
        self.published: list[OutboxMessage] = []
        self._fail_times = fail_times
        self._fail_forever = fail_forever
        self.attempts = 0

    def publish(self, message: OutboxMessage) -> None:
        self.attempts += 1
        if self._fail_forever or self.attempts <= self._fail_times:
            raise RuntimeError("simulated transport failure")
        self.published.append(message)


class HttpCallbackTransport:
    """POST the envelope to a configured endpoint (e.g. a Spring receiver).

    Spring's receiving contract is not finalised, so this stays optional and is
    only constructed when OUTBOX_HTTP_ENDPOINT is set.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        timeout_seconds: float = 10.0,
        auth_header: str | None = None,
    ):
        if not endpoint:
            raise ValueError("OUTBOX_HTTP_ENDPOINT is required")
        self._endpoint = endpoint
        self._timeout = timeout_seconds
        self._auth_header = auth_header

    def publish(self, message: OutboxMessage) -> None:
        import httpx

        headers = {"Content-Type": "application/json"}
        if self._auth_header:
            headers["Authorization"] = self._auth_header
        response = httpx.post(
            self._endpoint,
            content=message.to_json().encode("utf-8"),
            headers=headers,
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"outbox endpoint rejected the event: {response.status_code}"
            )


def emit_outbox_event(
    session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    project_id: str,
    payload: dict,
) -> OutboxEvent:
    """Stage one event on the CALLER's session and transaction.

    Not committing here is the whole point: the event becomes visible only if
    the domain change it describes also commits.
    """

    if event_type not in PIPELINE_EVENT_TYPES:
        raise ValueError(f"unsupported outbox event type: {event_type}")
    now = utcnow()
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        project_id=project_id,
        schema_version=SCHEMA_VERSION,
        payload=payload,
        status=PENDING,
        attempt_count=0,
        available_at=now,
        created_at=now,
    )
    session.add(event)
    return event


def _to_message(row: OutboxEvent) -> OutboxMessage:
    return OutboxMessage(
        event_id=str(row.id),
        event_type=row.event_type,
        aggregate_type=row.aggregate_type,
        aggregate_id=row.aggregate_id,
        project_id=row.project_id,
        schema_version=row.schema_version,
        occurred_at=row.created_at,
        payload=dict(row.payload or {}),
    )


@dataclass(frozen=True)
class PublishResult:
    claimed: int
    published: int
    failed: int
    dead: int


def publish_pending_events(
    session_factory,
    transport: OutboxTransport,
    *,
    batch_size: int = 20,
    stall_timeout_seconds: float = 300.0,
) -> PublishResult:
    """Claim a batch, publish each, and record the outcome per row.

    A row claimed by a worker that then dies is reclaimed automatically: the
    claim pushes ``available_at`` ``stall_timeout_seconds`` into the future, and
    PUBLISHING rows past that point are claimable again. That is what makes
    delivery at-least-once rather than at-most-once.
    """

    from datetime import timedelta

    session = session_factory()
    claimed: list[tuple[uuid.UUID, uuid.UUID, OutboxMessage]] = []
    try:
        now = utcnow()
        statement = (
            select(OutboxEvent)
            .where(
                OutboxEvent.status.in_((PENDING, PUBLISHING)),
                OutboxEvent.available_at <= now,
            )
            .order_by(OutboxEvent.available_at, OutboxEvent.created_at)
        )
        rows = claim_rows(session, statement, limit=batch_size)
        for row in rows:
            # PUBLISHING makes the claim durable, so a crash between claim and
            # delivery does not leave the row silently PENDING for another
            # worker to publish concurrently.
            claim_token = uuid.uuid4()
            row.status = PUBLISHING
            row.claim_token = claim_token
            row.claimed_at = now
            row.available_at = now + timedelta(seconds=stall_timeout_seconds)
            claimed.append((row.id, claim_token, _to_message(row)))
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    published = failed = dead = 0
    for event_id, claim_token, message in claimed:
        try:
            transport.publish(message)
        except Exception as exc:
            outcome = _record_failure(
                session_factory,
                event_id,
                claim_token,
                exc,
            )
            if outcome == DEAD:
                dead += 1
            elif outcome == PENDING:
                failed += 1
        else:
            if _record_success(session_factory, event_id, claim_token):
                published += 1

    return PublishResult(
        claimed=len(claimed),
        published=published,
        failed=failed,
        dead=dead,
    )


def _record_success(
    session_factory,
    event_id: uuid.UUID,
    claim_token: uuid.UUID,
) -> bool:
    session = session_factory()
    try:
        row = session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.status == PUBLISHING,
                OutboxEvent.claim_token == claim_token,
            )
            .with_for_update()
        ).scalar_one_or_none()
        # Only the worker that still holds the PUBLISHING claim may write the
        # outcome. A slow worker whose claim was reclaimed must not overwrite
        # the result of whoever took over.
        if row is None:
            session.rollback()
            return False
        now = utcnow()
        row.status = PUBLISHED
        row.claim_token = None
        row.published_at = now
        row.attempt_count += 1
        row.last_error = None
        session.commit()
        return True
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _record_failure(
    session_factory,
    event_id: uuid.UUID,
    claim_token: uuid.UUID,
    error: Exception,
) -> str | None:
    session = session_factory()
    try:
        row = session.execute(
            select(OutboxEvent)
            .where(
                OutboxEvent.id == event_id,
                OutboxEvent.status == PUBLISHING,
                OutboxEvent.claim_token == claim_token,
            )
            .with_for_update()
        ).scalar_one_or_none()
        # Same guard as _record_success: without it a slow worker could flip an
        # already-PUBLISHED row back to PENDING and cause a redelivery loop.
        if row is None:
            session.rollback()
            return None
        now = utcnow()
        row.attempt_count += 1
        row.last_error = f"{type(error).__name__}: {error}"[:2000]
        row.claim_token = None
        if row.attempt_count >= row.max_attempts:
            # Poison event: stop retrying so one bad row cannot stall the relay.
            row.status = DEAD
        else:
            row.status = PENDING
            row.available_at = now + backoff_delay(row.attempt_count)
        outcome = row.status
        session.commit()
        return outcome
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def build_transport_from_env():
    """Pick a transport from configuration; defaults to the recording fake."""

    import os

    name = os.getenv("OUTBOX_TRANSPORT", "fake").strip().lower()
    if name == "fake":
        return FakeOutboxTransport()
    if name == "http":
        return HttpCallbackTransport(
            os.getenv("OUTBOX_HTTP_ENDPOINT", ""),
            timeout_seconds=float(os.getenv("OUTBOX_HTTP_TIMEOUT_SECONDS", "10")),
            auth_header=os.getenv("OUTBOX_HTTP_AUTH_HEADER") or None,
        )
    raise ValueError(
        f"OUTBOX_TRANSPORT must be 'fake' or 'http'; got {name!r}. "
        "An SQS transport can be added once Spring's receiving contract is fixed."
    )


__all__ = [
    "ANALYSIS_QUEUED",
    "DEAD",
    "FINAL_REVIEW_READY",
    "INITIAL_REVIEW_READY",
    "PENDING",
    "PIPELINE_COMPLETED",
    "PIPELINE_EVENT_TYPES",
    "PIPELINE_FAILED",
    "PUBLISHED",
    "PUBLISHING",
    "SCHEMA_VERSION",
    "FakeOutboxTransport",
    "HttpCallbackTransport",
    "OutboxMessage",
    "OutboxTransport",
    "PublishResult",
    "build_transport_from_env",
    "emit_outbox_event",
    "publish_pending_events",
]
