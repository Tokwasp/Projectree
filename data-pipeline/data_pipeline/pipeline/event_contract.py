"""Python-owned Event Contract v1 and project graph snapshot helpers.

All helpers stage rows on the caller's transaction.  They never commit, which
keeps domain writes, graph-version increments, and outbox records atomic.
"""

from __future__ import annotations

import re
import uuid
from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from data_pipeline.storage import (
    AnalysisDeliveryState,
    Evidence,
    MeetingSummary,
    Node,
    NodeRevisionEvidence,
    OutboxEvent,
    ProjectGraphState,
)

EVENT_SCHEMA_VERSION = "1"
PROJECT_GRAPH_CHANGED = "PROJECT_GRAPH_CHANGED"
MEETING_SUMMARY_READY = "MEETING_SUMMARY_READY"
ANALYSIS_STATUS_CHANGED = "ANALYSIS_STATUS_CHANGED"

_SIGNED_INT64_MIN = -(2**63)
_SIGNED_INT64_MAX = 2**63 - 1
_CANONICAL_INTEGER = re.compile(r"0|-?[1-9][0-9]*\Z")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utc_z(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def public_identifier(value: str | int) -> str | int:
    """Return Java-long compatible identifiers as JSON numbers.

    UUIDs, OpenVidu room names, and other external identifiers remain strings.
    Non-canonical numeric strings (``01``, ``+1``, whitespace) deliberately stay
    strings so serialization cannot silently change their identity.
    """

    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        if _SIGNED_INT64_MIN <= value <= _SIGNED_INT64_MAX:
            return value
        return str(value)
    text = str(value)
    if _CANONICAL_INTEGER.fullmatch(text):
        parsed = int(text)
        if _SIGNED_INT64_MIN <= parsed <= _SIGNED_INT64_MAX:
            return parsed
    return text


def canonical_storage_identifier(value: str | int, *, field: str) -> str:
    """Validate numeric IDs without rejecting genuine external identifiers."""

    if isinstance(value, bool):
        raise ValueError(f"{field} must not be boolean")
    if isinstance(value, int):
        if not _SIGNED_INT64_MIN <= value <= _SIGNED_INT64_MAX:
            raise ValueError(f"{field} is outside signed 64-bit range")
        return str(value)
    text = str(value)
    if not text or text != text.strip():
        raise ValueError(f"{field} must be non-blank without surrounding whitespace")
    if _CANONICAL_INTEGER.fullmatch(text):
        parsed = int(text)
        if not _SIGNED_INT64_MIN <= parsed <= _SIGNED_INT64_MAX:
            raise ValueError(f"{field} is outside signed 64-bit range")
        return str(parsed)
    numeric_like = any(character.isdigit() for character in text) and all(
        character.isdigit() or character in "+-.eE" for character in text
    )
    if numeric_like:
        raise ValueError(f"{field} must be a canonical decimal integer")
    return text


def _evidence_snapshots(session, node: Node) -> list[dict]:
    if node.current_revision_id is None:
        return []
    rows = session.execute(
        select(Evidence)
        .join(NodeRevisionEvidence, NodeRevisionEvidence.evidence_id == Evidence.id)
        .where(
            NodeRevisionEvidence.project_id == node.project_id,
            NodeRevisionEvidence.node_revision_id == node.current_revision_id,
            Evidence.project_id == node.project_id,
        )
        .order_by(Evidence.created_at, Evidence.id)
    ).scalars()
    return [
        {
            "evidenceId": str(evidence.id),
            "sourceType": evidence.source_type,
            "meetingId": (
                public_identifier(evidence.external_meeting_id)
                if evidence.external_meeting_id is not None
                else None
            ),
            "segmentId": evidence.source_segment_id,
            "speakerLabel": evidence.speaker_label,
            # startMs is intentionally private to Python/STT and excluded from
            # Event v1. It remains available in the ordinary graph API.
            "endMs": evidence.end_ms,
            "quoteStart": evidence.quote_start,
            "quoteEnd": evidence.quote_end,
            "quotedText": evidence.quoted_text,
        }
        for evidence in rows
    ]


def node_snapshot(session, node: Node) -> dict:
    return {
        "nodeId": str(node.id),
        "nodeVersion": node.version,
        "nodeType": node.node_type,
        "category": node.category,
        "title": node.title,
        "content": node.content,
        "dueDate": node.due_date,
        "graphState": node.graph_state,
        "consistencyStatus": node.consistency_status,
        "parentNodeId": str(node.parent_id) if node.parent_id else None,
        "mergedIntoNodeId": (
            str(node.merged_into_node_id) if node.merged_into_node_id else None
        ),
        "originType": node.origin_type,
        "createdAt": utc_z(node.created_at),
        "updatedAt": utc_z(node.updated_at),
        "evidence": _evidence_snapshots(session, node),
    }


def deleted_node_snapshot(node: Node) -> dict:
    if node.deleted_at is None:
        raise ValueError("deleted Node snapshot requires deleted_at")
    return {
        "nodeId": str(node.id),
        "nodeVersion": node.version,
        "deletedAt": utc_z(node.deleted_at),
    }


def _stage_v1(
    session,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    project_id: str,
    payload: dict,
    occurred_at: datetime | None = None,
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        project_id=project_id,
        schema_version=EVENT_SCHEMA_VERSION,
        payload=deepcopy(payload),
        status="PENDING",
        attempt_count=0,
        available_at=occurred_at or utcnow(),
        created_at=occurred_at or utcnow(),
    )
    session.add(event)
    return event


def _locked_graph_state(session, *, project_id: str) -> ProjectGraphState | None:
    return session.execute(
        select(ProjectGraphState)
        .where(ProjectGraphState.project_id == project_id)
        .with_for_update()
    ).scalar_one_or_none()


def lock_project_graph_state(session, *, project_id: str) -> tuple[int, bool]:
    """Take the project-wide graph lock and report the current version.

    Returns ``(current_version, materialized_here)``.

    Every Java command that may bump the graph version takes this lock FIRST,
    before locking any Node row. The two resources are always acquired in the
    same order — coarse project row, then fine Node rows — so two concurrent
    commands can never hold one and wait on the other.

    A project whose graph has never changed has no row to lock, and absence of
    the row is the system-wide encoding of version 0. Such a row is created at
    0 purely as something to lock; a caller that ends without bumping must hand
    it back through :func:`release_unmutated_graph_state` so the encoding is
    restored.
    """

    state = _locked_graph_state(session, project_id=project_id)
    if state is not None:
        return state.graph_version, False
    table = ProjectGraphState.__table__
    values = {"project_id": project_id, "graph_version": 0}
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        statement = pg_insert(table).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(table).values(**values)
    else:
        session.add(ProjectGraphState(project_id=project_id, graph_version=0))
        session.flush()
        return _locked_graph_state(session, project_id=project_id).graph_version, True
    # RETURNING yields a row only when this statement performed the INSERT, so a
    # racing transaction that got there first is never mistaken for our own.
    inserted = session.execute(
        statement.on_conflict_do_nothing(
            index_elements=["project_id"]
        ).returning(table.c.project_id)
    ).first()
    session.flush()
    version = _locked_graph_state(session, project_id=project_id).graph_version
    return version, inserted is not None


def release_unmutated_graph_state(session, *, project_id: str) -> None:
    """Drop a lock-scaffolding row when the command bumped nothing."""

    state = _locked_graph_state(session, project_id=project_id)
    if state is not None and state.graph_version == 0:
        session.delete(state)
        session.flush()


def bump_graph_version(session, *, project_id: str) -> int:
    table = ProjectGraphState.__table__
    now = utcnow()
    values = {"project_id": project_id, "graph_version": 1, "updated_at": now}
    dialect = session.get_bind().dialect.name
    if dialect == "postgresql":
        statement = pg_insert(table).values(**values)
    elif dialect == "sqlite":
        statement = sqlite_insert(table).values(**values)
    else:
        row = session.get(ProjectGraphState, project_id)
        if row is None:
            row = ProjectGraphState(project_id=project_id, graph_version=1, updated_at=now)
            session.add(row)
        else:
            row.graph_version += 1
            row.updated_at = now
        session.flush()
        return row.graph_version
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.project_id],
        set_={
            "graph_version": table.c.graph_version + 1,
            "updated_at": now,
        },
    ).returning(table.c.graph_version)
    return int(session.execute(statement).scalar_one())


def stage_project_graph_changed(
    session,
    *,
    project_id: str,
    upserted_nodes: list[Node] | tuple[Node, ...] = (),
    deleted_nodes: list[Node] | tuple[Node, ...] = (),
) -> tuple[OutboxEvent, int]:
    """Increment once and emit one complete graph delta in the same tx."""

    session.flush()
    graph_version = bump_graph_version(session, project_id=project_id)
    upserts = sorted(
        (node_snapshot(session, node) for node in upserted_nodes),
        key=lambda item: item["nodeId"],
    )
    deletes = sorted(
        (deleted_node_snapshot(node) for node in deleted_nodes),
        key=lambda item: item["nodeId"],
    )
    payload = {
        "projectId": public_identifier(project_id),
        "graphVersion": graph_version,
        "upsertedNodes": upserts,
        "deletedNodes": deletes,
    }
    event = _stage_v1(
        session,
        event_type=PROJECT_GRAPH_CHANGED,
        aggregate_type="project_graph",
        aggregate_id=project_id,
        project_id=project_id,
        payload=payload,
    )
    return event, graph_version


def _delivery_state(
    session,
    *,
    project_id: str,
    external_meeting_id: str,
    lock: bool = True,
) -> AnalysisDeliveryState | None:
    statement = select(AnalysisDeliveryState).where(
        AnalysisDeliveryState.project_id == project_id,
        AnalysisDeliveryState.external_meeting_id == external_meeting_id,
    )
    if lock:
        statement = statement.with_for_update()
    return session.execute(statement).scalar_one_or_none()


def stage_analysis_processing(
    session,
    *,
    project_id: str,
    external_meeting_id: str,
) -> AnalysisDeliveryState:
    state = _delivery_state(
        session,
        project_id=project_id,
        external_meeting_id=external_meeting_id,
    )
    if state is None:
        state = AnalysisDeliveryState(
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            status="PROCESSING",
        )
        session.add(state)
        session.flush()
        _stage_analysis_event(session, state=state)
    elif state.status != "PROCESSING":
        # A new processing cycle explicitly clears the previous terminal data.
        state.status = "PROCESSING"
        state.required_graph_version = None
        state.required_summary_version = None
        state.failure_code = None
        state.failure_message = None
        state.updated_at = utcnow()
        _stage_analysis_event(session, state=state)
    return state


def stage_analysis_failed(
    session,
    *,
    project_id: str,
    external_meeting_id: str,
    failure_code: str,
    failure_message: str | None = None,
) -> AnalysisDeliveryState:
    state = _delivery_state(
        session,
        project_id=project_id,
        external_meeting_id=external_meeting_id,
    )
    if state is None:
        state = AnalysisDeliveryState(
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            status="FAILED",
        )
        session.add(state)
    elif state.status == "SUCCEEDED":
        return state
    state.status = "FAILED"
    state.failure_code = failure_code[:128]
    # Never pass raw transcript/provider material. Callers provide a sanitized
    # operational message; it is bounded again here.
    state.failure_message = failure_message[:500] if failure_message else None
    state.updated_at = utcnow()
    session.flush()
    _stage_analysis_event(session, state=state)
    return state


def mark_graph_ready(
    session,
    *,
    project_id: str,
    external_meeting_id: str,
    graph_version: int,
) -> AnalysisDeliveryState:
    state = _delivery_state(
        session,
        project_id=project_id,
        external_meeting_id=external_meeting_id,
    ) or stage_analysis_processing(
        session,
        project_id=project_id,
        external_meeting_id=external_meeting_id,
    )
    state.required_graph_version = graph_version
    state.updated_at = utcnow()
    try_complete_analysis(
        session,
        project_id=project_id,
        external_meeting_id=external_meeting_id,
    )
    return state


def try_complete_analysis(
    session,
    *,
    project_id: str,
    external_meeting_id: str,
) -> AnalysisDeliveryState | None:
    state = _delivery_state(
        session,
        project_id=project_id,
        external_meeting_id=external_meeting_id,
    )
    if state is None or state.status == "FAILED":
        return state
    if state.required_graph_version is None or state.required_summary_version is None:
        return state
    if state.status != "SUCCEEDED":
        state.status = "SUCCEEDED"
        state.updated_at = utcnow()
        session.flush()
        _stage_analysis_event(session, state=state)
    return state


def _stage_analysis_event(session, *, state: AnalysisDeliveryState) -> OutboxEvent:
    payload: dict = {
        "projectId": public_identifier(state.project_id),
        "externalMeetingId": public_identifier(state.external_meeting_id),
        "status": state.status,
    }
    if state.status == "SUCCEEDED":
        payload.update(
            requiredGraphVersion=state.required_graph_version,
            requiredSummaryVersion=state.required_summary_version,
        )
    elif state.status == "FAILED":
        payload["failureCode"] = state.failure_code
        if state.failure_message:
            payload["failureMessage"] = state.failure_message
    return _stage_v1(
        session,
        event_type=ANALYSIS_STATUS_CHANGED,
        aggregate_type="meeting_analysis",
        aggregate_id=f"{state.project_id}:{state.external_meeting_id}",
        project_id=state.project_id,
        payload=payload,
    )


def stage_meeting_summary_ready(
    session,
    *,
    summary: MeetingSummary,
    api_path: str,
) -> OutboxEvent:
    payload = {
        "meetingSummaryId": str(summary.id),
        "projectId": public_identifier(summary.project_id),
        "externalMeetingId": public_identifier(summary.external_meeting_id),
        "summaryVersion": summary.summary_version,
        "status": summary.status,
        "apiPath": api_path,
    }
    event = _stage_v1(
        session,
        event_type=MEETING_SUMMARY_READY,
        aggregate_type="meeting_summary",
        aggregate_id=str(summary.id),
        project_id=summary.project_id,
        payload=payload,
    )
    mark_summary_ready(session, summary=summary)
    return event


def mark_summary_ready(session, *, summary: MeetingSummary) -> AnalysisDeliveryState:
    state = _delivery_state(
        session,
        project_id=summary.project_id,
        external_meeting_id=summary.external_meeting_id,
    ) or stage_analysis_processing(
        session,
        project_id=summary.project_id,
        external_meeting_id=summary.external_meeting_id,
    )
    state.required_summary_version = summary.summary_version
    state.updated_at = utcnow()
    try_complete_analysis(
        session,
        project_id=summary.project_id,
        external_meeting_id=summary.external_meeting_id,
    )
    return state


__all__ = [
    "ANALYSIS_STATUS_CHANGED",
    "EVENT_SCHEMA_VERSION",
    "MEETING_SUMMARY_READY",
    "PROJECT_GRAPH_CHANGED",
    "bump_graph_version",
    "canonical_storage_identifier",
    "deleted_node_snapshot",
    "lock_project_graph_state",
    "mark_graph_ready",
    "mark_summary_ready",
    "node_snapshot",
    "public_identifier",
    "release_unmutated_graph_state",
    "stage_analysis_failed",
    "stage_analysis_processing",
    "stage_meeting_summary_ready",
    "stage_project_graph_changed",
    "try_complete_analysis",
    "utc_z",
]
