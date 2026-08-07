"""Deterministic immutable full-graph Snapshot v1."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from sqlalchemy import select

from data_pipeline.pipeline.event_contract import public_identifier, utc_z
from data_pipeline.storage import (
    Evidence,
    MergeOperation,
    Node,
    NodeRevisionEvidence,
)

GRAPH_SNAPSHOT_MAX_SIZE_ENV = "PROJECTREE_GRAPH_SNAPSHOT_MAX_SIZE_BYTES"
DEFAULT_GRAPH_SNAPSHOT_MAX_SIZE_BYTES = 10 * 1024 * 1024


class GraphSnapshotTooLargeError(ValueError):
    """Raised before publishing a Snapshot Java cannot accept."""


def graph_snapshot_max_size_bytes(value: str | int | None = None) -> int:
    raw_value = (
        os.getenv(
            GRAPH_SNAPSHOT_MAX_SIZE_ENV,
            str(DEFAULT_GRAPH_SNAPSHOT_MAX_SIZE_BYTES),
        )
        if value is None
        else value
    )
    try:
        limit = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{GRAPH_SNAPSHOT_MAX_SIZE_ENV} must be a positive integer"
        ) from exc
    if limit <= 0:
        raise ValueError(
            f"{GRAPH_SNAPSHOT_MAX_SIZE_ENV} must be a positive integer"
        )
    return limit


def validate_graph_snapshot_size(
    content: bytes,
    *,
    max_size_bytes: str | int | None = None,
) -> int:
    """Return the byte length when it is within Java's inclusive limit."""

    limit = graph_snapshot_max_size_bytes(max_size_bytes)
    size = len(content)
    if size > limit:
        raise GraphSnapshotTooLargeError(
            f"graph snapshot size {size} exceeds maximum {limit} bytes"
        )
    return size


def canonical_json_bytes(payload: dict) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _nodes(session, *, project_id: str) -> list[Node]:
    return list(
        session.execute(
            select(Node)
            .where(
                Node.project_id == project_id,
                Node.graph_state.in_(["ACTIVE", "UNATTACHED", "MERGED"]),
                Node.deleted_at.is_(None),
            )
            .order_by(Node.id)
        ).scalars()
    )


def build_full_graph_snapshot(
    session,
    *,
    project_id: str,
    meeting_id: str | None,
    command_id: str,
    graph_version: int,
    generated_at: datetime | None = None,
) -> dict:
    generated = generated_at or datetime.now(timezone.utc)
    nodes = _nodes(session, project_id=project_id)
    node_ids = [node.id for node in nodes]
    node_rows = [
        {
            "nodeId": str(node.id),
            "sourceMeetingId": public_identifier(node.source_meeting_id),
            "parentNodeId": str(node.parent_id) if node.parent_id else None,
            "mergedIntoNodeId": (
                str(node.merged_into_node_id) if node.merged_into_node_id else None
            ),
            "nodeType": node.node_type,
            "category": node.category,
            "graphState": node.graph_state,
            "title": node.title,
            "content": node.content,
            "linkSource": node.origin_type,
            "nodeVersion": node.version,
            "createdAt": utc_z(node.created_at),
            "updatedAt": utc_z(node.updated_at),
        }
        for node in nodes
    ]

    evidence_rows: list[dict] = []
    for node in nodes:
        if node.current_revision_id is None:
            continue
        evidences = list(
            session.execute(
                select(Evidence)
                .join(
                    NodeRevisionEvidence,
                    NodeRevisionEvidence.evidence_id == Evidence.id,
                )
                .where(
                    NodeRevisionEvidence.project_id == project_id,
                    NodeRevisionEvidence.node_revision_id == node.current_revision_id,
                    Evidence.project_id == project_id,
                )
                .order_by(Evidence.created_at, Evidence.id)
            ).scalars()
        )
        for order, evidence in enumerate(evidences, start=1):
            evidence_rows.append(
                {
                    "evidenceId": str(evidence.id),
                    "nodeId": str(node.id),
                    "meetingId": (
                        public_identifier(evidence.external_meeting_id)
                        if evidence.external_meeting_id is not None
                        else None
                    ),
                    "quoteText": evidence.quoted_text,
                    "speakerLabel": evidence.speaker_label,
                    "startMs": evidence.start_ms,
                    "endMs": evidence.end_ms,
                    "evidenceOrder": order,
                }
            )
    evidence_rows.sort(
        key=lambda row: (row["nodeId"], row["evidenceOrder"], row["evidenceId"])
    )

    merge_rows: list[dict] = []
    if node_ids:
        operations = session.execute(
            select(MergeOperation, Node)
            .join(Node, Node.id == MergeOperation.source_node_id)
            .where(
                MergeOperation.project_id == project_id,
                MergeOperation.status == "APPLIED",
                Node.project_id == project_id,
                Node.id.in_(node_ids),
                Node.graph_state == "MERGED",
                Node.deleted_at.is_(None),
            )
            .order_by(MergeOperation.source_node_id, MergeOperation.id)
        ).all()
        merge_rows = [
            {
                "mergeId": str(operation.id),
                "sourceNodeId": str(operation.source_node_id),
                "targetNodeId": str(operation.resolved_target_node_id),
                "sourceMeetingId": public_identifier(source.source_meeting_id),
                "mergedAt": utc_z(operation.applied_at),
            }
            for operation, source in operations
        ]

    return {
        "snapshotSchemaVersion": 1,
        "projectId": public_identifier(project_id),
        "meetingId": (
            public_identifier(meeting_id) if meeting_id is not None else None
        ),
        "commandId": command_id,
        "graphVersion": graph_version,
        "generatedAt": utc_z(generated),
        "nodes": node_rows,
        "evidences": evidence_rows,
        "mergeRecords": merge_rows,
    }


def snapshot_digest(payload: dict) -> tuple[bytes, str]:
    content = canonical_json_bytes(payload)
    return content, hashlib.sha256(content).hexdigest()


__all__ = [
    "DEFAULT_GRAPH_SNAPSHOT_MAX_SIZE_BYTES",
    "GRAPH_SNAPSHOT_MAX_SIZE_ENV",
    "GraphSnapshotTooLargeError",
    "build_full_graph_snapshot",
    "canonical_json_bytes",
    "graph_snapshot_max_size_bytes",
    "snapshot_digest",
    "validate_graph_snapshot_size",
]
