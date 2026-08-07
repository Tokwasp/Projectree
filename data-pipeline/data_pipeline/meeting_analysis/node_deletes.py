"""Node logical delete received from the Java command queue.

The command carries delete *seeds*.  The authoritative PostgreSQL graph decides
the effective set: every structural descendant of a seed, plus every MERGED
source that points into the set, transitively.  Java's projection is never
trusted for that derivation — it may lag the graph it is projecting.

One accepted command bumps ``graphVersion`` exactly once regardless of how many
Nodes it removes, and each removed Node takes one ``nodeVersion`` step through
the ordinary revision path.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from data_pipeline.pipeline.errors import GraphIntegrityError
from data_pipeline.pipeline.event_contract import (
    lock_project_graph_state,
    release_unmutated_graph_state,
)
from data_pipeline.pipeline.revisions import (
    create_node_revision,
    current_revision_evidence_specs,
    mark_node_embedding_stale,
)
from data_pipeline.storage import (
    GraphChangeEvent,
    GraphSnapshotArtifact,
    MeetingAnalysisCommand,
    Node,
    OutboxEvent,
    Relation,
)

from .contracts import NodeDeleteCommandMessage
from .persistence import CommandPayloadConflictError
from .result_events import (
    NODE_DELETE_REJECTED,
    PROJECT_GRAPH_CHANGED,
    stage_node_delete_rejected_v3,
    stage_project_graph_changed_v3,
)
from .snapshot import GraphSnapshotTooLargeError


NODE_DELETE_REQUESTED = "NODE_DELETE_REQUESTED"
NODE_DELETE_SOURCE = "NODE_DELETE"

# States a Node can be logically deleted from.  Anything else (already DELETED,
# EXCLUDED, ARCHIVED) is not a live graph Node and is reported as missing.
DELETABLE_STATES = ("ACTIVE", "MERGED", "UNATTACHED")


@dataclass(frozen=True)
class NodeDeleteResult:
    command_id: uuid.UUID
    status: str
    deleted_node_ids: tuple[uuid.UUID, ...] = ()
    graph_version: int | None = None
    changed: bool = False
    failure_code: str | None = None
    event_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None
    replayed: bool = False
    node_versions: dict[uuid.UUID, int] = field(default_factory=dict)


def _payload_hash(command: NodeDeleteCommandMessage) -> str:
    payload = {
        "commandSchemaVersion": 1,
        "commandId": str(command.command_id),
        "commandType": NODE_DELETE_REQUESTED,
        "requestedAt": command.requested_at.isoformat(),
        "projectId": command.project_id,
        "payload": {
            # Hashed in the order Java sent them: a different seed order is a
            # different payload, which is exactly what the conflict check means.
            "nodeIds": [str(node_id) for node_id in command.node_ids],
            "expectedGraphVersion": command.expected_graph_version,
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


def _new_inbox_row(
    *,
    command: NodeDeleteCommandMessage,
    payload_hash: str,
    status: str,
) -> MeetingAnalysisCommand:
    return MeetingAnalysisCommand(
        command_id=command.command_id,
        command_type=NODE_DELETE_REQUESTED,
        project_id=command.project_id,
        meeting_id=None,
        room_name=None,
        generate_summary=None,
        generate_nodes=None,
        target_node_id=None,
        expected_node_version=None,
        expected_graph_version=command.expected_graph_version,
        requested_by_member_id=command.requested_by_member_id,
        requested_at=command.requested_at,
        status=status,
        payload_hash=payload_hash,
    )


def _command_event(session, *, command_id: uuid.UUID, project_id: str, event_type: str):
    events = session.execute(
        select(OutboxEvent).where(
            OutboxEvent.project_id == project_id,
            OutboxEvent.event_type == event_type,
            OutboxEvent.schema_version == "3",
        )
    ).scalars().all()
    return next(
        (
            candidate
            for candidate in events
            if candidate.payload.get("commandId") == str(command_id)
        ),
        None,
    )


def _existing_result(
    session,
    *,
    command: NodeDeleteCommandMessage,
    row: MeetingAnalysisCommand,
) -> NodeDeleteResult:
    """Return the recorded outcome without staging anything a second time."""

    artifact = session.execute(
        select(GraphSnapshotArtifact).where(
            GraphSnapshotArtifact.project_id == command.project_id,
            GraphSnapshotArtifact.command_id == command.command_id,
        )
    ).scalar_one_or_none()
    event_type = (
        PROJECT_GRAPH_CHANGED if artifact is not None else NODE_DELETE_REJECTED
    )
    event = _command_event(
        session,
        command_id=command.command_id,
        project_id=command.project_id,
        event_type=event_type,
    )
    deleted_ids: tuple[uuid.UUID, ...] = ()
    if row.status == "COMPLETED":
        # The change log is the record of what *this* command removed; the
        # Node table also holds Nodes deleted by earlier commands.
        deleted_ids = tuple(
            session.execute(
                select(GraphChangeEvent.node_id)
                .where(
                    GraphChangeEvent.project_id == command.project_id,
                    GraphChangeEvent.request_id == str(command.command_id),
                    GraphChangeEvent.change_type.in_(
                        ["USER_DELETE_NODE", "USER_DELETE_MERGED"]
                    ),
                )
                .order_by(GraphChangeEvent.node_id)
            ).scalars()
        )
    return NodeDeleteResult(
        command_id=command.command_id,
        status=row.status,
        deleted_node_ids=deleted_ids,
        graph_version=artifact.graph_version if artifact is not None else None,
        changed=artifact is not None,
        failure_code=row.failure_code,
        event_id=event.id if event is not None else None,
        artifact_id=artifact.id if artifact is not None else None,
        replayed=True,
    )


def _reject(
    session,
    *,
    row: MeetingAnalysisCommand,
    command: NodeDeleteCommandMessage,
    reason_code: str,
    message: str,
    materialized_graph_state: bool,
) -> NodeDeleteResult:
    """Record the business rejection and its Result event in one commit."""

    row.status = "FAILED"
    row.failure_code = reason_code
    row.failure_message = message[:2000]
    event = stage_node_delete_rejected_v3(
        session,
        command=row,
        reason_code=reason_code,
    )
    if materialized_graph_state:
        # No graph mutation happened, so the project must go back to having no
        # row at all — that is what the graph-snapshot API reads as "absent".
        release_unmutated_graph_state(session, project_id=command.project_id)
    session.commit()
    return NodeDeleteResult(
        command_id=command.command_id,
        status="FAILED",
        failure_code=reason_code,
        event_id=event.id,
    )


def _record_infrastructure_failure(
    session_factory,
    *,
    command: NodeDeleteCommandMessage,
    payload_hash: str,
    code: str,
    message: str,
) -> NodeDeleteResult:
    """Persist a deterministic non-business failure after a rollback.

    No Result event is staged: Java is told about domain decisions, not about
    a Snapshot that Python itself refuses to publish.
    """

    session = session_factory()
    try:
        existing = session.execute(
            select(MeetingAnalysisCommand)
            .where(MeetingAnalysisCommand.command_id == command.command_id)
            .with_for_update()
        ).scalar_one_or_none()
        if existing is not None:
            if (
                existing.command_type != NODE_DELETE_REQUESTED
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
        return NodeDeleteResult(
            command_id=command.command_id,
            status="FAILED",
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
            return _record_infrastructure_failure(
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


def effective_delete_closure(
    session,
    *,
    project_id: str,
    seed_ids: set[uuid.UUID],
) -> dict[uuid.UUID, Node]:
    """Expand seeds over structural children and reverse merge edges.

    Both edge kinds are expanded in the same fixpoint loop, because a MERGED
    source pulled in by a reverse edge can itself own a subtree, and a
    descendant can itself be a merge target.
    """

    resolved: dict[uuid.UUID, Node] = {}
    frontier = list(seed_ids)
    while frontier:
        rows = list(
            session.execute(
                select(Node)
                .where(
                    Node.project_id == project_id,
                    Node.deleted_at.is_(None),
                    Node.graph_state.in_(DELETABLE_STATES),
                    (
                        Node.parent_id.in_(frontier)
                        | Node.merged_into_node_id.in_(frontier)
                    ),
                )
                .order_by(Node.id)
                .with_for_update()
            ).scalars()
        )
        frontier = []
        for row in rows:
            if row.id in resolved:
                continue
            resolved[row.id] = row
            frontier.append(row.id)
    return resolved


def _assert_no_dangling_references(
    session,
    *,
    project_id: str,
    delete_ids: set[uuid.UUID],
) -> None:
    """Fail loudly rather than commit a graph Java could not project.

    Scoped to the states the Snapshot carries. EXCLUDED and ARCHIVED Nodes keep
    their historical parent pointer on purpose (see `contracts.enums`), Java
    never sees them, and treating that retained pointer as corruption would
    turn an ordinary delete into an unretriable command.
    """

    dangling = session.execute(
        select(Node.id)
        .where(
            Node.project_id == project_id,
            Node.deleted_at.is_(None),
            Node.graph_state.in_(DELETABLE_STATES),
            Node.id.not_in(delete_ids),
            (
                Node.parent_id.in_(delete_ids)
                | Node.merged_into_node_id.in_(delete_ids)
            ),
        )
        .order_by(Node.id)
    ).scalars().all()
    if dangling:
        raise GraphIntegrityError(
            "delete closure left a live Node referencing a deleted Node: "
            + ", ".join(str(node_id) for node_id in dangling)
        )


def _expire_relations(session, *, project_id: str, delete_ids: list[uuid.UUID], now) -> None:
    for relation in session.execute(
        select(Relation).where(
            Relation.project_id == project_id,
            (
                Relation.from_node_id.in_(delete_ids)
                | Relation.to_node_id.in_(delete_ids)
            ),
            Relation.status == "CONFIRMED",
            Relation.valid_to.is_(None),
        )
    ).scalars():
        relation.status = "REJECTED"
        relation.valid_to = now


def _logically_delete(
    session,
    *,
    node: Node,
    command: NodeDeleteCommandMessage,
    now: datetime,
) -> None:
    before = {
        "nodeId": str(node.id),
        "graphState": node.graph_state,
        "version": node.version,
        "parentNodeId": str(node.parent_id) if node.parent_id else None,
        "mergedIntoNodeId": (
            str(node.merged_into_node_id) if node.merged_into_node_id else None
        ),
    }
    was_merged = node.graph_state == "MERGED"
    merged_into = node.merged_into_node_id
    specs = current_revision_evidence_specs(session, node=node)
    if node.current_revision_id is None:
        # A legacy projection has no Revision from which the helper can derive
        # the next version. The delete must still advance optimistic
        # concurrency exactly once.
        node.version += 1
    create_node_revision(
        session,
        node=node,
        title=node.title,
        content=node.content,
        node_type=node.node_type,
        category=node.category,
        due_date=node.due_date,
        created_by_type="USER",
        created_by_id=command.requested_by_member_id,
        generation_run_id=None,
        evidence_specs=specs,
        requires_evidence=bool(specs),
    )
    # ck_node_merge_shape and ck_node_deleted_shape only admit DELETED rows
    # whose merge pointer is cleared, so the pointers go before the state.
    node.parent_id = None
    node.merged_into_node_id = None
    node.graph_state = "DELETED"
    node.deleted_at = now
    node.deleted_by = command.requested_by_member_id
    node.last_actor_type = "USER"
    mark_node_embedding_stale(session, node=node)
    session.add(
        GraphChangeEvent(
            project_id=command.project_id,
            request_id=str(command.command_id),
            node_id=node.id,
            item_id=node.source_item_id,
            change_type="USER_DELETE_MERGED" if was_merged else "USER_DELETE_NODE",
            actor_type="USER",
            before=before,
            after={
                "nodeId": str(node.id),
                "graphState": node.graph_state,
                "version": node.version,
                "parentNodeId": None,
                "mergedIntoNodeId": None,
            },
            detail={
                "actorId": command.requested_by_member_id,
                "commandId": str(command.command_id),
                "sourceType": NODE_DELETE_SOURCE,
                "representativeNodeId": (
                    str(merged_into) if merged_into is not None else None
                ),
            },
        )
    )


def process_node_delete(
    session_factory,
    *,
    command: NodeDeleteCommandMessage,
) -> NodeDeleteResult:
    """Apply one delete command, its Snapshot artifact and its Result event."""

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
                existing.command_type != NODE_DELETE_REQUESTED
                or existing.payload_hash != payload_hash
            ):
                raise CommandPayloadConflictError("COMMAND_ID_PAYLOAD_CONFLICT")
            if existing.status in {"COMPLETED", "FAILED"}:
                result = _existing_result(session, command=command, row=existing)
                session.rollback()
                return result
            raise RuntimeError("Node delete command is already processing")

        row = _new_inbox_row(
            command=command,
            payload_hash=payload_hash,
            status="PROCESSING",
        )
        session.add(row)
        session.flush()

        # Project lock before any Node lock; see lock_project_graph_state.
        current_version, materialized = lock_project_graph_state(
            session, project_id=command.project_id
        )
        if current_version != command.expected_graph_version:
            return _reject(
                session,
                row=row,
                command=command,
                reason_code="GRAPH_VERSION_CONFLICT",
                message=(
                    f"expected graph version {command.expected_graph_version} "
                    f"but the project is at {current_version}"
                ),
                materialized_graph_state=materialized,
            )

        seed_ids = set(command.node_ids)
        seeds = {
            node.id: node
            for node in session.execute(
                select(Node)
                .where(Node.id.in_(seed_ids))
                .order_by(Node.id)
                .with_for_update()
            ).scalars()
        }
        missing = [
            node_id
            for node_id in command.node_ids
            if node_id not in seeds
            or seeds[node_id].deleted_at is not None
            or seeds[node_id].graph_state not in DELETABLE_STATES
        ]
        if missing:
            return _reject(
                session,
                row=row,
                command=command,
                reason_code="NODE_NOT_FOUND",
                message=(
                    "seed Node is missing or already deleted: "
                    + ", ".join(str(node_id) for node_id in missing)
                ),
                materialized_graph_state=materialized,
            )
        foreign = [
            node_id
            for node_id in command.node_ids
            if seeds[node_id].project_id != command.project_id
        ]
        if foreign:
            return _reject(
                session,
                row=row,
                command=command,
                reason_code="NODE_PROJECT_MISMATCH",
                message=(
                    "seed Node belongs to another project: "
                    + ", ".join(str(node_id) for node_id in foreign)
                ),
                materialized_graph_state=materialized,
            )

        closure = effective_delete_closure(
            session,
            project_id=command.project_id,
            seed_ids=seed_ids,
        )
        closure.update(seeds)
        delete_ids = sorted(closure)
        _assert_no_dangling_references(
            session,
            project_id=command.project_id,
            delete_ids=set(delete_ids),
        )

        now = datetime.now(timezone.utc)
        _expire_relations(
            session,
            project_id=command.project_id,
            delete_ids=delete_ids,
            now=now,
        )
        for node_id in delete_ids:
            _logically_delete(
                session,
                node=closure[node_id],
                command=command,
                now=now,
            )
        session.flush()
        _assert_no_dangling_references(
            session,
            project_id=command.project_id,
            delete_ids=set(delete_ids),
        )

        event, artifact, graph_version = stage_project_graph_changed_v3(
            session,
            command=row,
            source_type=NODE_DELETE_SOURCE,
        )
        row.status = "COMPLETED"
        row.failure_code = None
        row.failure_message = None
        node_versions = {node_id: closure[node_id].version for node_id in delete_ids}
        session.commit()
        return NodeDeleteResult(
            command_id=command.command_id,
            status="COMPLETED",
            deleted_node_ids=tuple(delete_ids),
            graph_version=graph_version,
            changed=True,
            event_id=event.id,
            artifact_id=artifact.id,
            node_versions=node_versions,
        )
    except GraphSnapshotTooLargeError as exc:
        session.rollback()
        return _record_infrastructure_failure(
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
            return process_node_delete(session_factory, command=command)
        raise
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "DELETABLE_STATES",
    "NODE_DELETE_REQUESTED",
    "NODE_DELETE_SOURCE",
    "NodeDeleteResult",
    "effective_delete_closure",
    "process_node_delete",
]
