"""Result Event v3 staging; no legacy all-tasks completion barrier."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from data_pipeline.pipeline.event_contract import (
    bump_graph_version,
    public_identifier,
)
from data_pipeline.storage import (
    GraphSnapshotArtifact,
    MeetingAnalysisCommand,
    MeetingSummary,
    OutboxEvent,
)

from .snapshot import (
    build_full_graph_snapshot,
    snapshot_digest,
    validate_graph_snapshot_size,
)

EVENT_SCHEMA_VERSION = "3"
PROJECT_GRAPH_CHANGED = "PROJECT_GRAPH_CHANGED"
MEETING_SUMMARY_READY = "MEETING_SUMMARY_READY"
ANALYSIS_TASK_STATUS_CHANGED = "ANALYSIS_TASK_STATUS_CHANGED"
NODE_DELETE_REJECTED = "NODE_DELETE_REJECTED"
NODE_CONTENT_UPDATE_REJECTED = "NODE_CONTENT_UPDATE_REJECTED"

NODE_DELETE_REJECTION_REASONS = frozenset(
    {
        "GRAPH_VERSION_CONFLICT",
        "NODE_NOT_FOUND",
        "NODE_PROJECT_MISMATCH",
    }
)

NODE_CONTENT_UPDATE_REJECTION_REASONS = frozenset(
    {
        "NODE_NOT_FOUND",
        "NODE_NOT_EDITABLE",
        "MERGED_SOURCE_NOT_EDITABLE",
        "NODE_VERSION_CONFLICT",
        "INVALID_CURRENT_REVISION",
        "NO_CHANGE",
        "GRAPH_SNAPSHOT_TOO_LARGE",
    }
)


def _stage_v3(
    session,
    *,
    event_type: str,
    command: MeetingAnalysisCommand,
    payload: dict,
    aggregate_type: str,
    aggregate_id: str,
) -> OutboxEvent:
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        project_id=command.project_id,
        schema_version=EVENT_SCHEMA_VERSION,
        payload={
            "meetingId": (
                public_identifier(command.meeting_id)
                if command.meeting_id is not None
                else None
            ),
            "commandId": str(command.command_id),
            "payload": payload,
        },
        status="PENDING",
        attempt_count=0,
        available_at=datetime.now(timezone.utc),
    )
    session.add(event)
    return event


def stage_project_graph_changed_v3(
    session,
    *,
    command: MeetingAnalysisCommand,
    snapshot_prefix: str | None = None,
    source_type: str = "MEETING_ANALYSIS",
) -> tuple[OutboxEvent, GraphSnapshotArtifact, int]:
    """Increment once, freeze the full snapshot, and stage the v3 event."""

    if source_type not in {
        "MEETING_ANALYSIS",
        "NODE_CONTENT_UPDATE",
        "NODE_DELETE",
    }:
        raise ValueError("unsupported PROJECT_GRAPH_CHANGED sourceType")

    session.flush()
    graph_version = bump_graph_version(session, project_id=command.project_id)
    snapshot = build_full_graph_snapshot(
        session,
        project_id=command.project_id,
        meeting_id=command.meeting_id,
        command_id=str(command.command_id),
        graph_version=graph_version,
    )
    content, digest = snapshot_digest(snapshot)
    size_bytes = validate_graph_snapshot_size(content)
    configured_prefix = snapshot_prefix or os.getenv(
        "PROJECTREE_GRAPH_SNAPSHOT_PREFIX", "graph-snapshots/"
    )
    prefix = configured_prefix.strip("/")
    if not prefix:
        raise ValueError("PROJECTREE_GRAPH_SNAPSHOT_PREFIX must not be blank")
    object_key = (
        f"{prefix}/project-{command.project_id}/"
        f"command-{command.command_id}/v{graph_version}.json"
    )
    artifact = GraphSnapshotArtifact(
        project_id=command.project_id,
        meeting_id=command.meeting_id,
        command_id=command.command_id,
        graph_version=graph_version,
        snapshot_schema_version=1,
        payload_json=snapshot,
        size_bytes=size_bytes,
        sha256=digest,
        content_type="application/json",
        object_key=object_key,
        status="PENDING",
    )
    session.add(artifact)
    session.flush()
    event = _stage_v3(
        session,
        event_type=PROJECT_GRAPH_CHANGED,
        command=command,
        aggregate_type="project_graph",
        aggregate_id=command.project_id,
        payload={
            "sourceType": source_type,
            "graphVersion": graph_version,
            "snapshotArtifactId": str(artifact.id),
        },
    )
    return event, artifact, graph_version


def stage_meeting_summary_ready_v3(
    session,
    *,
    command: MeetingAnalysisCommand,
    summary: MeetingSummary,
    api_path: str,
) -> OutboxEvent:
    return _stage_v3(
        session,
        event_type=MEETING_SUMMARY_READY,
        command=command,
        aggregate_type="meeting_summary",
        aggregate_id=str(summary.id),
        payload={
            "meetingSummaryId": str(summary.id),
            "summaryVersion": summary.summary_version,
            "status": summary.status,
            "apiPath": api_path,
        },
    )


def stage_node_delete_rejected_v3(
    session,
    *,
    command: MeetingAnalysisCommand,
    reason_code: str,
) -> OutboxEvent:
    """Stage the business rejection in the same transaction as the outcome.

    The payload carries only what Java's Node Delete contract agreed on. Seed
    ids and the observed graph versions stay in the command inbox row and the
    change log, where they serve diagnosis without widening the wire contract.

    Infrastructure failures never reach here: they roll the transaction back
    and are retried by the command queue instead of being reported to Java as
    a domain decision.
    """

    if reason_code not in NODE_DELETE_REJECTION_REASONS:
        raise ValueError(
            f"unsupported NODE_DELETE_REJECTED reasonCode: {reason_code}"
        )
    return _stage_v3(
        session,
        event_type=NODE_DELETE_REJECTED,
        command=command,
        aggregate_type="project_graph",
        aggregate_id=command.project_id,
        payload={
            "sourceType": "NODE_DELETE",
            "reasonCode": reason_code,
        },
    )


def stage_node_content_update_rejected_v3(
    session,
    *,
    command: MeetingAnalysisCommand,
    reason_code: str,
    failed_node_id: str | None,
) -> OutboxEvent:
    """Stage one terminal V2 Node update rejection for Java."""

    if reason_code not in NODE_CONTENT_UPDATE_REJECTION_REASONS:
        raise ValueError(
            f"unsupported NODE_CONTENT_UPDATE_REJECTED reasonCode: {reason_code}"
        )
    return _stage_v3(
        session,
        event_type=NODE_CONTENT_UPDATE_REJECTED,
        command=command,
        aggregate_type="project_graph",
        aggregate_id=command.project_id,
        payload={
            "sourceType": "NODE_CONTENT_UPDATE",
            "reasonCode": reason_code,
            "failedNodeId": failed_node_id,
        },
    )


def stage_task_failed_v3(
    session,
    *,
    command: MeetingAnalysisCommand,
    task_type: str,
    failure_code: str,
    failure_message: str | None = None,
) -> OutboxEvent:
    if task_type not in {"SUMMARY", "NODES"}:
        raise ValueError("task_type must be SUMMARY or NODES")
    normalized_code = failure_code.strip() if isinstance(failure_code, str) else ""
    if not normalized_code:
        raise ValueError("failure_code must not be blank")
    normalized_message = (
        failure_message.strip()
        if isinstance(failure_message, str) and failure_message.strip()
        else normalized_code
    )
    payload = {
        "taskType": task_type,
        "status": "FAILED",
        "failureCode": normalized_code[:100],
        "failureMessage": normalized_message[:1000],
    }
    return _stage_v3(
        session,
        event_type=ANALYSIS_TASK_STATUS_CHANGED,
        command=command,
        aggregate_type="meeting_analysis_task",
        aggregate_id=f"{command.command_id}:{task_type}",
        payload=payload,
    )


__all__ = [
    "ANALYSIS_TASK_STATUS_CHANGED",
    "EVENT_SCHEMA_VERSION",
    "MEETING_SUMMARY_READY",
    "NODE_DELETE_REJECTED",
    "NODE_DELETE_REJECTION_REASONS",
    "NODE_CONTENT_UPDATE_REJECTED",
    "NODE_CONTENT_UPDATE_REJECTION_REASONS",
    "PROJECT_GRAPH_CHANGED",
    "stage_meeting_summary_ready_v3",
    "stage_node_delete_rejected_v3",
    "stage_node_content_update_rejected_v3",
    "stage_project_graph_changed_v3",
    "stage_task_failed_v3",
]
