"""Atomic canonical Node content updates received from the Java command queue."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from data_pipeline.retrieval.embedding import (
    CurrentRevisionEmbeddingError,
    load_current_revision_embedding_input,
)
from data_pipeline.storage import (
    GraphChangeEvent,
    GraphSnapshotArtifact,
    MeetingAnalysisCommand,
    Node,
    NodeAnalysisRun,
    NodeRevision,
    OutboxEvent,
)
from data_pipeline.pipeline.revisions import (
    create_node_revision,
    current_revision_evidence_specs,
    reconcile_embedding_status_after_revision,
)

from .contracts import NodeContentUpdateCommandMessage
from .persistence import CommandPayloadConflictError
from .result_events import stage_project_graph_changed_v3
from .snapshot import GraphSnapshotTooLargeError


NODE_CONTENT_UPDATE_REQUESTED = "NODE_CONTENT_UPDATE_REQUESTED"
NODE_CONTENT_UPDATE_SOURCE = "NODE_CONTENT_UPDATE"


@dataclass(frozen=True)
class NodeContentUpdateResult:
    command_id: uuid.UUID
    status: str
    node_id: uuid.UUID
    node_version: int | None
    graph_version: int | None
    changed: bool
    failure_code: str | None = None
    event_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None
    replayed: bool = False


def _payload_hash(command: NodeContentUpdateCommandMessage) -> str:
    payload = {
        "commandSchemaVersion": 1,
        "commandId": str(command.command_id),
        "commandType": NODE_CONTENT_UPDATE_REQUESTED,
        "requestedAt": command.requested_at.isoformat(),
        "projectId": command.project_id,
        "payload": {
            "nodeId": str(command.node_id),
            "expectedNodeVersion": command.expected_node_version,
            "title": command.title,
            "content": command.content,
            "requestedByMemberId": command.requested_by_member_id,
        },
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _existing_result(
    session,
    *,
    command: NodeContentUpdateCommandMessage,
    row: MeetingAnalysisCommand,
) -> NodeContentUpdateResult:
    artifact = session.execute(
        select(GraphSnapshotArtifact).where(
            GraphSnapshotArtifact.project_id == command.project_id,
            GraphSnapshotArtifact.command_id == command.command_id,
        )
    ).scalar_one_or_none()
    event = session.execute(
        select(OutboxEvent).where(
            OutboxEvent.project_id == command.project_id,
            OutboxEvent.event_type == "PROJECT_GRAPH_CHANGED",
            OutboxEvent.schema_version == "3",
            OutboxEvent.aggregate_id == command.project_id,
        )
    ).scalars().all()
    matching_event = next(
        (
            candidate
            for candidate in event
            if candidate.payload.get("commandId") == str(command.command_id)
        ),
        None,
    )
    snapshot_node = (
        next(
            (
                item
                for item in artifact.payload_json.get("nodes", [])
                if item.get("nodeId") == str(command.node_id)
            ),
            None,
        )
        if artifact is not None
        else None
    )
    node_version = (
        snapshot_node.get("nodeVersion")
        if snapshot_node is not None
        else row.expected_node_version
        if row.status == "COMPLETED"
        else None
    )
    return NodeContentUpdateResult(
        command_id=command.command_id,
        status=row.status,
        node_id=command.node_id,
        node_version=node_version,
        graph_version=artifact.graph_version if artifact is not None else None,
        changed=artifact is not None,
        failure_code=row.failure_code,
        event_id=matching_event.id if matching_event is not None else None,
        artifact_id=artifact.id if artifact is not None else None,
        replayed=True,
    )


def _record_failure(
    session,
    *,
    row: MeetingAnalysisCommand,
    command: NodeContentUpdateCommandMessage,
    code: str,
    message: str,
) -> NodeContentUpdateResult:
    row.status = "FAILED"
    row.failure_code = code
    row.failure_message = message[:2000]
    session.commit()
    return NodeContentUpdateResult(
        command_id=command.command_id,
        status="FAILED",
        node_id=command.node_id,
        node_version=None,
        graph_version=None,
        changed=False,
        failure_code=code,
    )


def _new_inbox_row(
    *,
    command: NodeContentUpdateCommandMessage,
    payload_hash: str,
    status: str,
) -> MeetingAnalysisCommand:
    return MeetingAnalysisCommand(
        command_id=command.command_id,
        command_type=NODE_CONTENT_UPDATE_REQUESTED,
        project_id=command.project_id,
        meeting_id=None,
        room_name=None,
        generate_summary=None,
        generate_nodes=None,
        target_node_id=command.node_id,
        expected_node_version=command.expected_node_version,
        requested_by_member_id=command.requested_by_member_id,
        requested_at=command.requested_at,
        status=status,
        payload_hash=payload_hash,
    )


def _persist_terminal_failure(
    session_factory,
    *,
    command: NodeContentUpdateCommandMessage,
    payload_hash: str,
    code: str,
    message: str,
) -> NodeContentUpdateResult:
    """Record a deterministic failure after the mutation transaction rolled back."""

    session = session_factory()
    try:
        existing = session.execute(
            select(MeetingAnalysisCommand)
            .where(MeetingAnalysisCommand.command_id == command.command_id)
            .with_for_update()
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.command_type != NODE_CONTENT_UPDATE_REQUESTED
                or existing.payload_hash != payload_hash
            ):
                raise CommandPayloadConflictError("COMMAND_ID_PAYLOAD_CONFLICT")
            result = _existing_result(session, command=command, row=existing)
            session.rollback()
            return result
        row = _new_inbox_row(
            command=command,
            payload_hash=payload_hash,
            status="FAILED",
        )
        row.failure_code = code
        row.failure_message = message[:2000]
        session.add(row)
        session.commit()
        return NodeContentUpdateResult(
            command_id=command.command_id,
            status="FAILED",
            node_id=command.node_id,
            node_version=None,
            graph_version=None,
            changed=False,
            failure_code=code,
        )
    except IntegrityError:
        session.rollback()
        verification = session_factory()
        try:
            concurrent = verification.execute(
                select(MeetingAnalysisCommand.id).where(
                    MeetingAnalysisCommand.command_id == command.command_id
                )
            ).scalar_one_or_none()
        finally:
            verification.close()
        if concurrent is not None:
            return _persist_terminal_failure(
                session_factory,
                command=command,
                payload_hash=payload_hash,
                code=code,
                message=message,
            )
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _current_embedding_hash(session, *, node: Node) -> str | None:
    try:
        return load_current_revision_embedding_input(session, node=node).text_hash
    except CurrentRevisionEmbeddingError:
        return None


def _invalidate_analysis(session, *, node: Node) -> None:
    run = None
    if node.current_analysis_run_id is not None:
        run = session.execute(
            select(NodeAnalysisRun)
            .where(
                NodeAnalysisRun.id == node.current_analysis_run_id,
                NodeAnalysisRun.source_node_id == node.id,
            )
            .with_for_update()
        ).scalar_one_or_none()
    if run is not None and run.status in {"PENDING", "RUNNING", "COMPLETED"}:
        run.status = "SUPERSEDED"
        run.completed_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)
    node.analysis_status = "STALE"
    node.analysis_input_hash = None


def process_node_content_update(
    session_factory,
    *,
    command: NodeContentUpdateCommandMessage,
) -> NodeContentUpdateResult:
    """Apply one command, its snapshot artifact and outbox row in one commit."""

    payload_hash = _payload_hash(command)
    session = session_factory()
    try:
        existing = session.execute(
            select(MeetingAnalysisCommand)
            .where(MeetingAnalysisCommand.command_id == command.command_id)
            .with_for_update()
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.command_type != NODE_CONTENT_UPDATE_REQUESTED
                or existing.payload_hash != payload_hash
            ):
                raise CommandPayloadConflictError(
                    "COMMAND_ID_PAYLOAD_CONFLICT"
                )
            if existing.status in {"COMPLETED", "FAILED"}:
                result = _existing_result(session, command=command, row=existing)
                session.rollback()
                return result
            raise RuntimeError("Node update command is already processing")

        row = _new_inbox_row(
            command=command,
            payload_hash=payload_hash,
            status="PROCESSING",
        )
        session.add(row)
        session.flush()

        node = session.execute(
            select(Node)
            .where(
                Node.id == command.node_id,
                Node.project_id == command.project_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if node is None:
            return _record_failure(
                session,
                row=row,
                command=command,
                code="NODE_NOT_FOUND",
                message="Node is missing or belongs to another project",
            )
        if (
            node.deleted_at is not None
            or node.graph_state in {"DELETED", "ARCHIVED", "EXCLUDED"}
        ):
            return _record_failure(
                session,
                row=row,
                command=command,
                code="NODE_NOT_EDITABLE",
                message="deleted, archived, or excluded Nodes are not editable",
            )
        if node.graph_state == "MERGED" or node.merged_into_node_id is not None:
            return _record_failure(
                session,
                row=row,
                command=command,
                code="MERGED_SOURCE_NOT_EDITABLE",
                message="edit the canonical merge target instead",
            )
        if node.graph_state not in {"ACTIVE", "UNATTACHED"}:
            return _record_failure(
                session,
                row=row,
                command=command,
                code="NODE_NOT_EDITABLE",
                message="only ACTIVE or UNATTACHED canonical Nodes are editable",
            )
        if node.version != command.expected_node_version:
            return _record_failure(
                session,
                row=row,
                command=command,
                code="NODE_VERSION_CONFLICT",
                message="expected Node version does not match current version",
            )

        next_title = command.title.strip() if command.title is not None else node.title
        next_content = command.content if command.content is not None else node.content
        if next_title == node.title and next_content == node.content:
            row.status = "COMPLETED"
            session.commit()
            return NodeContentUpdateResult(
                command_id=command.command_id,
                status="COMPLETED",
                node_id=node.id,
                node_version=node.version,
                graph_version=None,
                changed=False,
            )

        current_revision = (
            session.get(NodeRevision, node.current_revision_id)
            if node.current_revision_id is not None
            else None
        )
        if current_revision is None:
            return _record_failure(
                session,
                row=row,
                command=command,
                code="INVALID_CURRENT_REVISION",
                message="Node has no valid current Revision",
            )
        before = {
            "nodeId": str(node.id),
            "title": node.title,
            "content": node.content,
            "nodeType": node.node_type,
            "category": node.category,
            "graphState": node.graph_state,
            "version": node.version,
        }
        old_embedding_hash = _current_embedding_hash(session, node=node)
        evidence_specs = current_revision_evidence_specs(session, node=node)
        if current_revision.requires_evidence and not evidence_specs:
            return _record_failure(
                session,
                row=row,
                command=command,
                code="INVALID_CURRENT_REVISION",
                message="current Revision has no required Evidence",
            )
        create_node_revision(
            session,
            node=node,
            title=next_title,
            content=next_content,
            node_type=node.node_type,
            category=node.category,
            due_date=node.due_date,
            created_by_type="USER",
            created_by_id=command.requested_by_member_id,
            generation_run_id=None,
            evidence_specs=evidence_specs,
            requires_evidence=current_revision.requires_evidence,
            legacy_imported=current_revision.legacy_imported,
        )
        new_embedding_hash = _current_embedding_hash(session, node=node)
        reconcile_embedding_status_after_revision(session, node=node)
        if old_embedding_hash != new_embedding_hash:
            _invalidate_analysis(session, node=node)

        session.add(
            GraphChangeEvent(
                project_id=command.project_id,
                request_id=str(command.command_id),
                node_id=node.id,
                item_id=node.source_item_id,
                change_type="USER_EDIT_NODE",
                actor_type="USER",
                before=before,
                after={
                    "nodeId": str(node.id),
                    "title": node.title,
                    "content": node.content,
                    "nodeType": node.node_type,
                    "category": node.category,
                    "graphState": node.graph_state,
                    "version": node.version,
                },
                detail={
                    "actorId": command.requested_by_member_id,
                    "commandId": str(command.command_id),
                    "sourceType": NODE_CONTENT_UPDATE_SOURCE,
                    "analysisInvalidated": old_embedding_hash != new_embedding_hash,
                },
            )
        )
        event, artifact, graph_version = stage_project_graph_changed_v3(
            session,
            command=row,
            source_type=NODE_CONTENT_UPDATE_SOURCE,
        )
        row.status = "COMPLETED"
        row.failure_code = None
        row.failure_message = None
        session.commit()
        return NodeContentUpdateResult(
            command_id=command.command_id,
            status="COMPLETED",
            node_id=node.id,
            node_version=node.version,
            graph_version=graph_version,
            changed=True,
            event_id=event.id,
            artifact_id=artifact.id,
        )
    except GraphSnapshotTooLargeError as exc:
        session.rollback()
        return _persist_terminal_failure(
            session_factory,
            command=command,
            payload_hash=payload_hash,
            code="GRAPH_SNAPSHOT_TOO_LARGE",
            message=str(exc),
        )
    except IntegrityError:
        session.rollback()
        verification = session_factory()
        try:
            concurrent = verification.execute(
                select(MeetingAnalysisCommand.id).where(
                    MeetingAnalysisCommand.command_id == command.command_id
                )
            ).scalar_one_or_none()
        finally:
            verification.close()
        if concurrent is not None:
            return process_node_content_update(session_factory, command=command)
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "NODE_CONTENT_UPDATE_REQUESTED",
    "NODE_CONTENT_UPDATE_SOURCE",
    "NodeContentUpdateResult",
    "process_node_content_update",
]
