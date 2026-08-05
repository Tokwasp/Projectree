"""Canonical graph reads and reversible logical merge operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from data_pipeline.storage import (
    GraphChangeEvent,
    MergeOperation,
    MergeOperationDependency,
    MeetingAnalysisCommand,
    Node,
    NodeMergeHistory,
    NodeRevision,
    NodeRevisionEvidence,
    OutboxEvent,
    Relation,
)

from .errors import (
    GraphIntegrityError,
    GraphMutationValidationError,
    MergeNotReversibleError,
)
from .revisions import mark_node_embedding_stale
from .event_contract import stage_project_graph_changed

_CANONICAL_STATES = {"ACTIVE", "UNATTACHED"}
_MAX_CANONICAL_HOPS = 128


@dataclass(frozen=True)
class CanonicalRelation:
    relation_id: uuid.UUID
    relation_type: str
    original_from_node_id: uuid.UUID
    original_to_node_id: uuid.UUID
    canonical_from_node_id: uuid.UUID
    canonical_to_node_id: uuid.UUID


def parse_uuid(value: str | uuid.UUID, *, field: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise GraphMutationValidationError(f"{field} must be a UUID") from exc


def _node_in_any_project(session, node_id: uuid.UUID) -> Node | None:
    return session.execute(select(Node).where(Node.id == node_id)).scalar_one_or_none()


def get_project_node(
    session,
    *,
    project_id: str,
    node_id: str | uuid.UUID,
    for_update: bool = False,
    include_deleted: bool = False,
) -> Node:
    parsed = parse_uuid(node_id, field="node_id")
    statement = select(Node).where(
        Node.id == parsed,
        Node.project_id == project_id,
    )
    if not include_deleted:
        statement = statement.where(Node.deleted_at.is_(None))
    if for_update:
        statement = statement.with_for_update()
    node = session.execute(statement).scalar_one_or_none()
    if node is not None:
        return node
    if _node_in_any_project(session, parsed) is not None:
        raise GraphMutationValidationError("node belongs to another project")
    raise GraphMutationValidationError(f"node not found: {parsed}")


def resolve_canonical_node(
    session,
    *,
    project_id: str,
    node_id: str | uuid.UUID,
    expected_node_type: str | None = None,
    for_update: bool = False,
) -> Node:
    """Resolve a merge chain without mutating relation endpoints.

    Missing links, cross-project links, type changes, cycles, and excessive
    chains are stored-data corruption and therefore abort the caller.
    """

    current = get_project_node(
        session,
        project_id=project_id,
        node_id=node_id,
        for_update=for_update,
    )
    expected = expected_node_type or current.node_type
    visited: set[uuid.UUID] = set()
    for _ in range(_MAX_CANONICAL_HOPS):
        if current.id in visited:
            raise GraphIntegrityError(
                f"merge cycle detected at Node {current.id}"
            )
        visited.add(current.id)
        if current.node_type != expected:
            raise GraphIntegrityError(
                "merge chain changes Node type: "
                f"expected={expected}, actual={current.node_type}"
            )
        if current.graph_state != "MERGED":
            if current.merged_into_node_id is not None:
                raise GraphIntegrityError(
                    "non-MERGED Node has merged_into_node_id"
                )
            if current.graph_state not in _CANONICAL_STATES:
                raise GraphMutationValidationError(
                    f"canonical target is not available: {current.graph_state}"
                )
            return current
        if current.merged_into_node_id is None:
            raise GraphIntegrityError("MERGED Node has no target")
        next_node = session.execute(
            select(Node)
            .where(
                Node.id == current.merged_into_node_id,
                Node.project_id == project_id,
                Node.deleted_at.is_(None),
            )
            .with_for_update(of=Node) if for_update else
            select(Node).where(
                Node.id == current.merged_into_node_id,
                Node.project_id == project_id,
                Node.deleted_at.is_(None),
            )
        ).scalar_one_or_none()
        if next_node is None:
            other = _node_in_any_project(session, current.merged_into_node_id)
            if other is not None:
                raise GraphIntegrityError("merge chain crosses project boundary")
            raise GraphIntegrityError("merge chain points to a missing Node")
        current = next_node
    raise GraphIntegrityError("merge chain exceeds the canonical hop limit")


def list_canonical_relations(
    session,
    *,
    project_id: str,
) -> list[CanonicalRelation]:
    """Read relation endpoints through canonical Nodes; stored rows stay immutable."""

    result: list[CanonicalRelation] = []
    seen: set[tuple[uuid.UUID, uuid.UUID, str]] = set()
    relations = session.execute(
        select(Relation).where(
            Relation.project_id == project_id,
            Relation.status == "CONFIRMED",
            Relation.valid_to.is_(None),
        )
    ).scalars()
    for relation in relations:
        from_node = resolve_canonical_node(
            session,
            project_id=project_id,
            node_id=relation.from_node_id,
        )
        to_node = resolve_canonical_node(
            session,
            project_id=project_id,
            node_id=relation.to_node_id,
        )
        if from_node.id == to_node.id:
            continue
        key = (from_node.id, to_node.id, relation.relation_type)
        if relation.relation_type == "RELATED_TO":
            ordered = tuple(sorted((from_node.id, to_node.id), key=str))
            key = (ordered[0], ordered[1], relation.relation_type)
        if key in seen:
            continue
        seen.add(key)
        result.append(
            CanonicalRelation(
                relation_id=relation.id,
                relation_type=relation.relation_type,
                original_from_node_id=relation.from_node_id,
                original_to_node_id=relation.to_node_id,
                canonical_from_node_id=from_node.id,
                canonical_to_node_id=to_node.id,
            )
        )
    return result


def _audit_and_outbox(
    session,
    *,
    project_id: str,
    node: Node,
    change_type: str,
    actor_type: str,
    request_id: str | None,
    before: dict,
    detail: dict,
    emit_legacy_outbox: bool = True,
) -> None:
    after = {
        "nodeId": str(node.id),
        "graphState": node.graph_state,
        "mergedIntoNodeId": (
            str(node.merged_into_node_id)
            if node.merged_into_node_id is not None
            else None
        ),
        "version": node.version,
    }
    session.add(
        GraphChangeEvent(
            project_id=project_id,
            request_id=request_id,
            node_id=node.id,
            change_type=change_type,
            actor_type=actor_type,
            before=before,
            after=after,
            detail=detail,
        )
    )
    if emit_legacy_outbox:
        session.add(
            OutboxEvent(
            event_type="GRAPH_CHANGED",
            aggregate_type="node",
            aggregate_id=str(node.id),
            project_id=project_id,
            schema_version="auto-graph-v1",
            payload={
                "changeType": change_type,
                "nodeId": str(node.id),
                **detail,
            },
            status="PENDING",
            )
        )


def apply_logical_merge(
    session,
    *,
    project_id: str,
    source: Node,
    target: Node,
    actor_type: str,
    actor_id: str | None,
    generation_run_id: uuid.UUID | None,
    reason_code: str,
    reason_text: str | None,
    identity_basis: dict | None,
    conflicts_checked: dict | None,
    model_confidence: float | None,
    retrieval_rank: int | None,
    retrieval_score: float | None,
    second_retrieval_score: float | None,
) -> MergeOperation:
    """Merge by redirecting only the source; target content/evidence stay untouched."""

    if source.project_id != project_id or target.project_id != project_id:
        raise GraphMutationValidationError("merge Nodes must belong to the project")
    if source.id == target.id:
        raise GraphMutationValidationError("a Node cannot merge into itself")
    if source.graph_state not in _CANONICAL_STATES or source.merged_into_node_id:
        raise GraphMutationValidationError("merge source is not available")
    if source.node_type != target.node_type:
        raise GraphMutationValidationError("merge Nodes must have the same type")
    canonical_target = resolve_canonical_node(
        session,
        project_id=project_id,
        node_id=target.id,
        expected_node_type=source.node_type,
        for_update=True,
    )
    if canonical_target.id == source.id:
        raise GraphMutationValidationError("merge would create a cycle")
    if source.current_revision_id is None or canonical_target.current_revision_id is None:
        raise GraphIntegrityError("merge Nodes must have current revisions")

    source_version = source.version
    target_version = canonical_target.version
    now = datetime.now(timezone.utc)
    operation = MergeOperation(
        project_id=project_id,
        source_node_id=source.id,
        source_version=source_version,
        target_node_id=target.id,
        target_version=target_version,
        resolved_target_node_id=canonical_target.id,
        source_original_graph_state=source.graph_state,
        actor_type=actor_type,
        actor_id=actor_id,
        generation_run_id=generation_run_id,
        reason_code=reason_code,
        reason_text=reason_text,
        identity_basis=identity_basis,
        conflicts_checked=conflicts_checked,
        model_confidence=model_confidence,
        retrieval_rank=retrieval_rank,
        retrieval_score=retrieval_score,
        second_retrieval_score=second_retrieval_score,
        status="APPLIED",
        applied_at=now,
    )
    session.add(operation)
    session.flush()

    incoming_operations = session.execute(
        select(MergeOperation).where(
            MergeOperation.project_id == project_id,
            MergeOperation.status == "APPLIED",
            MergeOperation.resolved_target_node_id == source.id,
            MergeOperation.id != operation.id,
        )
    ).scalars()
    for dependency in incoming_operations:
        session.add(
            MergeOperationDependency(
                project_id=project_id,
                operation_id=operation.id,
                depends_on_operation_id=dependency.id,
            )
        )

    before = {
        "nodeId": str(source.id),
        "graphState": source.graph_state,
        "mergedIntoNodeId": None,
        "version": source.version,
    }
    source.graph_state = "MERGED"
    source.merged_into_node_id = canonical_target.id
    source.version += 1
    source.last_actor_type = actor_type
    source.updated_at = now
    mark_node_embedding_stale(session, node=source)

    # Compatibility projection for existing Evidence aggregation. A repeated
    # merge after unmerge is represented only by MergeOperation because this
    # legacy table intentionally has one row per source.
    history = session.execute(
        select(NodeMergeHistory).where(
            NodeMergeHistory.source_node_id == source.id
        )
    ).scalar_one_or_none()
    if history is None:
        session.add(
            NodeMergeHistory(
                project_id=project_id,
                source_node_id=source.id,
                target_node_id=canonical_target.id,
                analysis_run_id=None,
                candidate_id=None,
                approved_by=actor_id or actor_type,
                approved_at=now,
                source_version=source_version,
                target_version=target_version,
                merged_title=canonical_target.title,
                merged_content=canonical_target.content,
            )
        )

    _audit_and_outbox(
        session,
        project_id=project_id,
        node=source,
        change_type="LOGICAL_MERGE",
        actor_type=actor_type,
        request_id=str(generation_run_id) if generation_run_id else None,
        before=before,
        detail={
            "mergeOperationId": str(operation.id),
            "targetNodeId": str(target.id),
            "resolvedTargetNodeId": str(canonical_target.id),
            "reasonCode": reason_code,
        },
        emit_legacy_outbox=(
            session.execute(
                select(MeetingAnalysisCommand.id).where(
                    MeetingAnalysisCommand.project_id == project_id,
                    MeetingAnalysisCommand.meeting_id == source.source_meeting_id,
                )
            ).scalar_one_or_none()
            is None
        ),
    )
    session.flush()
    return operation


def unmerge_operation(
    session_factory,
    *,
    project_id: str,
    operation_id: str | uuid.UUID,
    actor_id: str,
) -> MergeOperation:
    """Undo one logical merge in reverse dependency order.

    The target snapshot is never restored or modified, so later user edits to
    the target remain intact.
    """

    parsed_id = parse_uuid(operation_id, field="operation_id")
    session = session_factory()
    try:
        operation = session.execute(
            select(MergeOperation)
            .where(
                MergeOperation.id == parsed_id,
                MergeOperation.project_id == project_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if operation is None:
            raise GraphMutationValidationError("merge operation not found")
        if operation.status == "REVERTED":
            session.rollback()
            return operation
        dependent = session.execute(
            select(MergeOperation.id)
            .join(
                MergeOperationDependency,
                MergeOperationDependency.operation_id == MergeOperation.id,
            )
            .where(
                MergeOperationDependency.project_id == project_id,
                MergeOperationDependency.depends_on_operation_id == operation.id,
                MergeOperation.status == "APPLIED",
            )
        ).scalar_one_or_none()
        if dependent is not None:
            raise MergeNotReversibleError(
                "a dependent merge must be undone first"
            )
        source = get_project_node(
            session,
            project_id=project_id,
            node_id=operation.source_node_id,
            for_update=True,
        )
        if (
            source.graph_state != "MERGED"
            or source.merged_into_node_id != operation.resolved_target_node_id
        ):
            raise GraphIntegrityError(
                "source Node no longer matches the merge operation"
            )
        revision = session.execute(
            select(NodeRevision).where(
                NodeRevision.id == source.current_revision_id,
                NodeRevision.project_id == project_id,
                NodeRevision.node_id == source.id,
            )
        ).scalar_one_or_none()
        if revision is None:
            raise GraphIntegrityError(
                "merge source has no recoverable current revision"
            )
        if revision.requires_evidence:
            evidence_exists = session.execute(
                select(NodeRevisionEvidence.evidence_id).where(
                    NodeRevisionEvidence.project_id == project_id,
                    NodeRevisionEvidence.node_revision_id == revision.id,
                )
            ).scalars().first()
            if evidence_exists is None:
                raise GraphIntegrityError(
                    "merge source revision has no recoverable Evidence"
                )
        target = get_project_node(
            session,
            project_id=project_id,
            node_id=operation.resolved_target_node_id,
            for_update=True,
        )
        before = {
            "nodeId": str(source.id),
            "graphState": source.graph_state,
            "mergedIntoNodeId": str(source.merged_into_node_id),
            "version": source.version,
        }
        source.graph_state = operation.source_original_graph_state
        source.merged_into_node_id = None
        source.version += 1
        source.last_actor_type = "USER"
        source.updated_at = datetime.now(timezone.utc)
        if target.version != operation.target_version:
            source.consistency_status = "NEEDS_ATTENTION"
        mark_node_embedding_stale(session, node=source)
        operation.status = "REVERTED"
        operation.reverted_at = datetime.now(timezone.utc)
        operation.reverted_by = actor_id
        _audit_and_outbox(
            session,
            project_id=project_id,
            node=source,
            change_type="LOGICAL_UNMERGE",
            actor_type="USER",
            request_id=None,
            before=before,
            detail={
                "mergeOperationId": str(operation.id),
                "actorId": actor_id,
            },
        )
        stage_project_graph_changed(
            session,
            project_id=project_id,
            upserted_nodes=[source, target],
        )
        session.commit()
        return operation
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "CanonicalRelation",
    "apply_logical_merge",
    "get_project_node",
    "list_canonical_relations",
    "parse_uuid",
    "resolve_canonical_node",
    "unmerge_operation",
]
