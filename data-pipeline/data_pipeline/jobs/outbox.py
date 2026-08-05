"""Transactional outbox: emission helper, transport port, and relay.

The outbox does not replace the queue. It exists so a domain state change and
the notification about it either both commit or neither does. Delivery is
**at-least-once**: the relay may publish an event twice (for example when the
transport succeeds but the status write is lost), so consumers must deduplicate
on ``eventId``. This is deliberately not exactly-once.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import select

from data_pipeline.storage import GraphSnapshotArtifact, OutboxEvent

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
MEETING_SUMMARY_READY = "MEETING_SUMMARY_READY"

PIPELINE_EVENT_TYPES = frozenset(
    {
        INITIAL_REVIEW_READY,
        ANALYSIS_QUEUED,
        FINAL_REVIEW_READY,
        PIPELINE_COMPLETED,
        PIPELINE_FAILED,
        MEETING_SUMMARY_READY,
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
        if self.schema_version == "3":
            occurred_at = self.occurred_at
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
            envelope = dict(self.payload)
            return {
                "eventSchemaVersion": 3,
                "eventId": self.event_id,
                "eventType": self.event_type,
                "occurredAt": occurred_at.astimezone(timezone.utc).isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z"),
                "projectId": _public_result_identifier(self.project_id),
                "meetingId": envelope["meetingId"],
                "commandId": envelope["commandId"],
                "payload": envelope["payload"],
            }
        if self.schema_version == "1":
            occurred_at = self.occurred_at
            if occurred_at.tzinfo is None:
                occurred_at = occurred_at.replace(tzinfo=timezone.utc)
            occurred_at = occurred_at.astimezone(timezone.utc)
            project_id: str | int = self.project_id
            canonical_numeric = (
                self.project_id == "0"
                or (
                    self.project_id.isdigit()
                    and not self.project_id.startswith("0")
                )
                or (
                    self.project_id.startswith("-")
                    and self.project_id[1:].isdigit()
                    and self.project_id[1:2] not in {"", "0"}
                )
            )
            if canonical_numeric:
                parsed = int(self.project_id)
                if -(2**63) <= parsed <= 2**63 - 1:
                    project_id = parsed
            return {
                "eventSchemaVersion": 1,
                "eventId": self.event_id,
                "eventType": self.event_type,
                "occurredAt": occurred_at.isoformat(timespec="microseconds").replace(
                    "+00:00", "Z"
                ),
                "projectId": project_id,
                "payload": self.payload,
            }
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


def _public_result_identifier(value: str) -> str | int:
    if value.isdigit() and (value == "0" or not value.startswith("0")):
        parsed = int(value)
        if -(2**63) <= parsed <= 2**63 - 1:
            return parsed
    return value


class S3ClaimCheckSqsTransport:
    """Publish Result Event v3, uploading graph artifacts before queue send."""

    def __init__(
        self,
        *,
        session_factory,
        s3_client,
        sqs_client,
        queue_url: str,
        snapshot_bucket: str,
        queue_type: str = "STANDARD",
        snapshot_max_size_bytes: str | int | None = None,
    ) -> None:
        queue_type = queue_type.strip().upper()
        if queue_type not in {"STANDARD", "FIFO"}:
            raise ValueError("queue_type must be STANDARD or FIFO")
        if not queue_url or not snapshot_bucket:
            raise ValueError("result queue URL and snapshot bucket are required")
        self._session_factory = session_factory
        self._s3 = s3_client
        self._sqs = sqs_client
        self._queue_url = queue_url
        self._bucket = snapshot_bucket
        self._queue_type = queue_type
        from data_pipeline.meeting_analysis.snapshot import (
            graph_snapshot_max_size_bytes,
        )

        self._snapshot_max_size_bytes = graph_snapshot_max_size_bytes(
            snapshot_max_size_bytes
        )

    def publish(self, message: OutboxMessage) -> None:
        if message.schema_version != "3":
            raise ValueError(
                "the Java result queue accepts only Result Event schema v3"
            )
        outgoing = message
        if message.schema_version == "3" and message.event_type == "PROJECT_GRAPH_CHANGED":
            outgoing = self._materialize_snapshot_ref(message)
        parameters: dict[str, object] = {
            "QueueUrl": self._queue_url,
            "MessageBody": outgoing.to_json(),
        }
        if self._queue_type == "FIFO":
            parameters["MessageGroupId"] = str(
                _public_result_identifier(outgoing.project_id)
            )
            parameters["MessageDeduplicationId"] = outgoing.event_id
        self._sqs.send_message(**parameters)

    def _materialize_snapshot_ref(self, message: OutboxMessage) -> OutboxMessage:
        envelope = dict(message.payload)
        payload = dict(envelope.get("payload") or {})
        artifact_id = payload.pop("snapshotArtifactId", None)
        if not isinstance(artifact_id, str):
            raise ValueError("PROJECT_GRAPH_CHANGED has no snapshotArtifactId")
        session = self._session_factory()
        try:
            artifact = session.execute(
                select(GraphSnapshotArtifact)
                .where(GraphSnapshotArtifact.id == uuid.UUID(artifact_id))
                .with_for_update()
            ).scalar_one()
            from data_pipeline.meeting_analysis.snapshot import (
                canonical_json_bytes,
                validate_graph_snapshot_size,
            )

            content = canonical_json_bytes(dict(artifact.payload_json))
            digest = hashlib.sha256(content).hexdigest()
            if len(content) != artifact.size_bytes or digest != artifact.sha256:
                raise RuntimeError("stored graph snapshot artifact checksum mismatch")
            validate_graph_snapshot_size(
                content,
                max_size_bytes=self._snapshot_max_size_bytes,
            )
            self._s3.put_object(
                Bucket=self._bucket,
                Key=artifact.object_key,
                Body=content,
                ContentType=artifact.content_type,
            )
            artifact.status = "UPLOADED"
            artifact.uploaded_at = utcnow()
            session.commit()
            payload["snapshotRef"] = {
                "bucket": self._bucket,
                "objectKey": artifact.object_key,
                "contentType": artifact.content_type,
                "sizeBytes": artifact.size_bytes,
                "sha256": artifact.sha256,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        envelope["payload"] = payload
        return OutboxMessage(
            event_id=message.event_id,
            event_type=message.event_type,
            aggregate_type=message.aggregate_type,
            aggregate_id=message.aggregate_id,
            project_id=message.project_id,
            schema_version=message.schema_version,
            occurred_at=message.occurred_at,
            payload=envelope,
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
    schema_versions: tuple[str, ...] | None = None,
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
        if schema_versions is not None:
            if not schema_versions:
                raise ValueError("schema_versions must not be empty")
            statement = statement.where(
                OutboxEvent.schema_version.in_(schema_versions)
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


def build_transport_from_env(*, session_factory=None):
    """Pick a transport from configuration; defaults to the recording fake."""

    import os

    name = os.getenv("OUTBOX_TRANSPORT", "fake").strip().lower()
    if name == "fake":
        app_env = os.getenv("APP_ENV", "local").strip().lower()
        if app_env not in {"test", "local", "development", "dev"}:
            raise RuntimeError(
                "OUTBOX_TRANSPORT=fake is forbidden outside local/test"
            )
        return FakeOutboxTransport()
    if name == "http":
        return HttpCallbackTransport(
            os.getenv("OUTBOX_HTTP_ENDPOINT", ""),
            timeout_seconds=float(os.getenv("OUTBOX_HTTP_TIMEOUT_SECONDS", "10")),
            auth_header=os.getenv("OUTBOX_HTTP_AUTH_HEADER") or None,
        )
    if name in {"result-sqs", "sqs"}:
        if session_factory is None:
            raise ValueError("session_factory is required for result-sqs transport")
        import boto3

        region = os.getenv("AWS_REGION", "ap-northeast-2")
        return S3ClaimCheckSqsTransport(
            session_factory=session_factory,
            s3_client=boto3.client("s3", region_name=region),
            sqs_client=boto3.client("sqs", region_name=region),
            queue_url=os.getenv("PROJECTREE_ANALYSIS_RESULT_QUEUE_URL", ""),
            snapshot_bucket=os.getenv("AWS_S3_BUCKET", ""),
            queue_type=os.getenv(
                "PROJECTREE_ANALYSIS_RESULT_QUEUE_TYPE", "STANDARD"
            ),
        )
    raise ValueError(
        f"OUTBOX_TRANSPORT must be 'fake', 'http', or 'result-sqs'; got {name!r}."
    )


__all__ = [
    "ANALYSIS_QUEUED",
    "DEAD",
    "FINAL_REVIEW_READY",
    "INITIAL_REVIEW_READY",
    "PENDING",
    "PIPELINE_COMPLETED",
    "PIPELINE_EVENT_TYPES",
    "MEETING_SUMMARY_READY",
    "PIPELINE_FAILED",
    "PUBLISHED",
    "PUBLISHING",
    "SCHEMA_VERSION",
    "FakeOutboxTransport",
    "HttpCallbackTransport",
    "OutboxMessage",
    "OutboxTransport",
    "S3ClaimCheckSqsTransport",
    "PublishResult",
    "build_transport_from_env",
    "emit_outbox_event",
    "publish_pending_events",
]
