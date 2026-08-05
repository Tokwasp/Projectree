"""User post-edit services for the automatically published graph."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from data_pipeline.storage import (
    GenerationRun,
    GraphChangeEvent,
    MergeOperation,
    MergeOperationDependency,
    MeetingAnalysisCommand,
    Node,
    NodeRevision,
    NodeRevisionEvidence,
    OutboxEvent,
    Relation,
)

from .errors import (
    GraphIntegrityError,
    GraphMutationValidationError,
    MergeNotReversibleError,
    NodeHasChildrenError,
    NodeVersionConflict,
)
from .graph import (
    apply_logical_merge,
    get_project_node,
    parse_uuid,
    resolve_canonical_node,
    unmerge_operation,
)
from .event_contract import stage_project_graph_changed
from data_pipeline.meeting_analysis.result_events import (
    stage_project_graph_changed_v3,
)
from .revisions import (
    create_node_revision,
    current_revision_evidence_specs,
    mark_node_embedding_stale,
    reconcile_embedding_status_after_revision,
    user_assertion_evidence,
)


@dataclass(frozen=True)
class UserGraphMutationResult:
    node_id: uuid.UUID
    version: int
    graph_state: str
    operation_id: uuid.UUID | None = None
    relation_id: uuid.UUID | None = None
    changed: bool = True


def _event(
    session,
    *,
    project_id: str,
    node: Node,
    actor_id: str,
    request_id: str | None,
    change_type: str,
    before: dict,
    detail: dict | None = None,
) -> None:
    after = {
        "nodeId": str(node.id),
        "title": node.title,
        "content": node.content,
        "nodeType": node.node_type,
        "category": node.category,
        "graphState": node.graph_state,
        "version": node.version,
    }
    session.add(
        GraphChangeEvent(
            project_id=project_id,
            request_id=request_id,
            node_id=node.id,
            change_type=change_type,
            actor_type="USER",
            before=before,
            after=after,
            detail={"actorId": actor_id, **(detail or {})},
        )
    )
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
                "actorId": actor_id,
                **(detail or {}),
            },
            status="PENDING",
        )
    )


def edit_node(
    session_factory,
    *,
    project_id: str,
    node_id: str | uuid.UUID,
    actor_id: str,
    request_id: str | None,
    expected_version: int,
    title: str | None = None,
    content: str | None = None,
    node_type: str | None = None,
    category: str | None = None,
    due_date: str | None = None,
    evidence_assertion: str | None = None,
    new_parent_node_id: str | uuid.UUID | None = None,
) -> UserGraphMutationResult:
    session = session_factory()
    try:
        node = get_project_node(
            session,
            project_id=project_id,
            node_id=node_id,
            for_update=True,
        )
        if node.graph_state in {"MERGED", "DELETED", "ARCHIVED", "EXCLUDED"}:
            raise GraphMutationValidationError(
                "edit the available canonical Node instead"
            )
        if node.version != expected_version:
            raise NodeVersionConflict(
                str(node.id), expected_version, node.version
            )
        next_title = title.strip() if title is not None else node.title
        next_content = content if content is not None else node.content
        next_type = node_type or node.node_type
        next_category = category or node.category
        next_due = due_date if due_date is not None else node.due_date
        if not next_title:
            raise GraphMutationValidationError("title must not be blank")
        if next_type not in {"DECISION", "ACTION", "ISSUE"}:
            raise GraphMutationValidationError("unsupported Node type")
        specs = current_revision_evidence_specs(session, node=node)
        if evidence_assertion is not None:
            specs.append(user_assertion_evidence(evidence_assertion))
        if not specs:
            raise GraphMutationValidationError(
                "an edit requires retained Evidence or a user assertion"
            )
        changed = any(
            (
                next_title != node.title,
                next_content != node.content,
                next_type != node.node_type,
                next_category != node.category,
                next_due != node.due_date,
                evidence_assertion is not None,
                new_parent_node_id is not None,
            )
        )
        if not changed:
            session.rollback()
            return UserGraphMutationResult(
                node_id=node.id,
                version=node.version,
                graph_state=node.graph_state,
                changed=False,
            )
        before = {
            "nodeId": str(node.id),
            "title": node.title,
            "content": node.content,
            "nodeType": node.node_type,
            "category": node.category,
            "version": node.version,
        }
        # v2: the canonical meaning hash decides, not a field-by-field diff.
        # Category is deliberately absent here - a Category-only edit keeps the
        # vector READY and costs no provider call.
        embedding_changed = any(
            (
                next_title != node.title,
                next_content != node.content,
                next_type != node.node_type,
                evidence_assertion is not None,
            )
        )
        category_changed = next_category != node.category
        subtree = [node]
        if category_changed:
            subtree = _active_subtree(
                session,
                project_id=project_id,
                root=node,
            )
            if next_type in {"ACTION", "ISSUE"}:
                if new_parent_node_id is None:
                    raise GraphMutationValidationError(
                        "CATEGORY_REPARENT_REQUIRED: Action/Issue category changes require newParentNodeId"
                    )
                _reparent_for_category_change(
                    session,
                    project_id=project_id,
                    node=node,
                    next_node_type=next_type,
                    next_category=next_category,
                    new_parent_node_id=new_parent_node_id,
                    subtree_ids={item.id for item in subtree},
                )
            elif new_parent_node_id is not None:
                raise GraphMutationValidationError(
                    "Decision category changes do not accept newParentNodeId"
                )
        elif new_parent_node_id is not None:
            _reparent_for_category_change(
                session,
                project_id=project_id,
                node=node,
                next_node_type=next_type,
                next_category=next_category,
                new_parent_node_id=new_parent_node_id,
                subtree_ids={node.id},
            )

        create_node_revision(
            session,
            node=node,
            title=next_title,
            content=next_content,
            node_type=next_type,
            category=next_category,
            due_date=next_due,
            created_by_type="USER",
            created_by_id=actor_id,
            generation_run_id=None,
            evidence_specs=specs,
            requires_evidence=True,
        )
        if embedding_changed:
            # Hash-based: reconcile rather than blanket-invalidate, so an edit
            # that happens to leave the canonical text identical stays READY.
            reconcile_embedding_status_after_revision(session, node=node)
        if category_changed:
            for descendant in subtree[1:]:
                descendant_specs = current_revision_evidence_specs(
                    session,
                    node=descendant,
                )
                create_node_revision(
                    session,
                    node=descendant,
                    title=descendant.title,
                    content=descendant.content,
                    node_type=descendant.node_type,
                    category=next_category,
                    due_date=descendant.due_date,
                    created_by_type="USER",
                    created_by_id=actor_id,
                    generation_run_id=None,
                    evidence_specs=descendant_specs,
                    requires_evidence=bool(descendant_specs),
                )
        if next_type != before["nodeType"]:
            _reconcile_edited_node_structure(
                session,
                project_id=project_id,
                node=node,
            )
            _mark_structural_dependents_for_attention(
                session,
                project_id=project_id,
                parent_node_id=node.id,
            )
        _event(
            session,
            project_id=project_id,
            node=node,
            actor_id=actor_id,
            request_id=request_id,
            change_type="USER_EDIT_NODE",
            before=before,
        )
        stage_project_graph_changed(
            session,
            project_id=project_id,
            upserted_nodes=subtree,
        )
        session.commit()
        return UserGraphMutationResult(
            node_id=node.id,
            version=node.version,
            graph_state=node.graph_state,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_user_node(
    session_factory,
    *,
    project_id: str,
    actor_id: str,
    request_id: str | None,
    node_type: str,
    category: str,
    title: str,
    content: str,
    due_date: str | None,
    evidence_assertion: str,
    external_meeting_id: str | None,
) -> UserGraphMutationResult:
    if node_type not in {"DECISION", "ACTION", "ISSUE"}:
        raise GraphMutationValidationError("unsupported Node type")
    session = session_factory()
    try:
        node = Node(
            project_id=project_id,
            source_meeting_id=external_meeting_id or "USER_CREATED",
            source_item_id=f"user-{uuid.uuid4()}",
            node_type=node_type,
            category=category,
            title=title.strip(),
            content=content,
            graph_state=("ACTIVE" if node_type == "DECISION" else "UNATTACHED"),
            analysis_status="ANALYZED",
            due_date=due_date,
            version=1,
            origin_type="USER_CREATED",
            last_actor_type="USER",
            consistency_status="NORMAL",
            confirmed_by=actor_id,
            confirmed_at=datetime.now(timezone.utc),
        )
        session.add(node)
        session.flush()
        create_node_revision(
            session,
            node=node,
            title=node.title,
            content=node.content,
            node_type=node.node_type,
            category=node.category,
            due_date=node.due_date,
            created_by_type="USER",
            created_by_id=actor_id,
            generation_run_id=None,
            evidence_specs=[user_assertion_evidence(evidence_assertion)],
            requires_evidence=True,
        )
        _event(
            session,
            project_id=project_id,
            node=node,
            actor_id=actor_id,
            request_id=request_id,
            change_type="USER_CREATE_NODE",
            before={},
        )
        stage_project_graph_changed(
            session,
            project_id=project_id,
            upserted_nodes=[node],
        )
        session.commit()
        return UserGraphMutationResult(
            node_id=node.id,
            version=node.version,
            graph_state=node.graph_state,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _mark_structural_dependents_for_attention(
    session,
    *,
    project_id: str,
    parent_node_id: uuid.UUID,
) -> None:
    relations = session.execute(
        select(Relation).where(
            Relation.project_id == project_id,
            Relation.to_node_id == parent_node_id,
            Relation.relation_type == "ATTACHED_TO",
            Relation.status == "CONFIRMED",
            Relation.valid_to.is_(None),
        )
    ).scalars()
    for relation in relations:
        child = session.execute(
            select(Node).where(
                Node.id == relation.from_node_id,
                Node.project_id == project_id,
            )
        ).scalar_one_or_none()
        if child is not None and child.graph_state not in {"DELETED", "MERGED"}:
            child.consistency_status = "NEEDS_ATTENTION"


def _active_subtree(
    session,
    *,
    project_id: str,
    root: Node,
) -> list[Node]:
    """Load and lock an ACTIVE descendant tree with explicit cycle defense."""

    result = [root]
    visited = {root.id}
    frontier = [root.id]
    while frontier:
        children = list(
            session.execute(
                select(Node)
                .where(
                    Node.project_id == project_id,
                    Node.parent_id.in_(frontier),
                    Node.graph_state == "ACTIVE",
                    Node.deleted_at.is_(None),
                )
                .order_by(Node.id)
                .with_for_update()
            ).scalars()
        )
        frontier = []
        for child in children:
            if child.id in visited:
                raise GraphIntegrityError("category subtree contains a cycle")
            visited.add(child.id)
            result.append(child)
            frontier.append(child.id)
    return result


def _structural_descendants_for_delete(
    session,
    *,
    project_id: str,
    root_id: uuid.UUID,
) -> list[Node]:
    """Lock every descendant that would otherwise retain an invalid parent."""

    result: list[Node] = []
    visited = {root_id}
    frontier = [root_id]
    while frontier:
        rows = list(
            session.execute(
                select(Node)
                .where(
                    Node.project_id == project_id,
                    Node.parent_id.in_(frontier),
                    Node.graph_state.in_(["ACTIVE", "UNATTACHED"]),
                    Node.deleted_at.is_(None),
                )
                .order_by(Node.id)
                .with_for_update()
            ).scalars()
        )
        frontier = []
        for row in rows:
            if row.id in visited:
                raise GraphIntegrityError("delete subtree contains a cycle")
            visited.add(row.id)
            result.append(row)
            frontier.append(row.id)
    return result


def _reparent_for_category_change(
    session,
    *,
    project_id: str,
    node: Node,
    next_node_type: str,
    next_category: str,
    new_parent_node_id: str | uuid.UUID,
    subtree_ids: set[uuid.UUID],
) -> None:
    if next_node_type not in {"ACTION", "ISSUE"}:
        raise GraphMutationValidationError(
            "only Action/Issue Nodes accept a structural parent"
        )
    parent = resolve_canonical_node(
        session,
        project_id=project_id,
        node_id=new_parent_node_id,
        for_update=True,
    )
    allowed = {"DECISION"} if next_node_type == "ACTION" else {"DECISION", "ACTION"}
    if (
        parent.id in subtree_ids
        or parent.deleted_at is not None
        or parent.graph_state != "ACTIVE"
        or parent.merged_into_node_id is not None
        or parent.node_type not in allowed
        or parent.category != next_category
    ):
        raise GraphMutationValidationError(
            "newParentNodeId is not a valid ACTIVE canonical parent in the new category"
        )
    ancestor = parent
    seen: set[uuid.UUID] = set()
    while ancestor.parent_id is not None:
        if ancestor.id in seen or ancestor.id in subtree_ids:
            raise GraphMutationValidationError("new parent would create a cycle")
        seen.add(ancestor.id)
        ancestor = get_project_node(
            session,
            project_id=project_id,
            node_id=ancestor.parent_id,
            for_update=True,
            include_deleted=True,
        )
        if ancestor.deleted_at is not None or ancestor.category != next_category:
            raise GraphMutationValidationError(
                "new parent chain crosses a deleted or different-category Node"
            )
    now = datetime.now(timezone.utc)
    for relation in session.execute(
        select(Relation)
        .where(
            Relation.project_id == project_id,
            Relation.from_node_id == node.id,
            Relation.relation_type == "ATTACHED_TO",
            Relation.status == "CONFIRMED",
            Relation.valid_to.is_(None),
        )
        .with_for_update()
    ).scalars():
        relation.status = "REJECTED"
        relation.valid_to = now
    relation = session.execute(
        select(Relation).where(
            Relation.project_id == project_id,
            Relation.from_node_id == node.id,
            Relation.to_node_id == parent.id,
            Relation.relation_type == "ATTACHED_TO",
        )
    ).scalar_one_or_none()
    if relation is None:
        relation = Relation(
            project_id=project_id,
            from_node_id=node.id,
            to_node_id=parent.id,
            relation_type="ATTACHED_TO",
            status="CONFIRMED",
            actor_type="USER",
            valid_from=now,
        )
        session.add(relation)
    else:
        relation.status = "CONFIRMED"
        relation.valid_from = now
        relation.valid_to = None
        relation.actor_type = "USER"
    node.parent_id = parent.id
    node.graph_state = "ACTIVE"
    node.consistency_status = "NORMAL"


def _reconcile_edited_node_structure(
    session,
    *,
    project_id: str,
    node: Node,
) -> None:
    """Keep the structural-parent invariant after a user changes Node type."""

    attached = list(
        session.execute(
            select(Relation)
            .where(
                Relation.project_id == project_id,
                Relation.from_node_id == node.id,
                Relation.relation_type == "ATTACHED_TO",
                Relation.status == "CONFIRMED",
                Relation.valid_to.is_(None),
            )
            .with_for_update()
        ).scalars()
    )
    now = datetime.now(timezone.utc)
    if node.node_type == "DECISION":
        for relation in attached:
            relation.status = "REJECTED"
            relation.valid_to = now
        node.parent_id = None
        node.graph_state = "ACTIVE"
        return

    allowed = (
        {"DECISION"}
        if node.node_type == "ACTION"
        else {"DECISION", "ACTION"}
    )
    valid: list[tuple[Relation, Node]] = []
    for relation in attached:
        parent = resolve_canonical_node(
            session,
            project_id=project_id,
            node_id=relation.to_node_id,
            for_update=True,
        )
        if parent.graph_state == "ACTIVE" and parent.node_type in allowed:
            valid.append((relation, parent))
        else:
            relation.status = "REJECTED"
            relation.valid_to = now
    if len(valid) > 1:
        raise GraphIntegrityError(
            "Node has multiple active structural parents"
        )
    if valid:
        node.parent_id = valid[0][1].id
        node.graph_state = "ACTIVE"
        node.consistency_status = "NORMAL"
        return
    node.parent_id = None
    node.graph_state = "UNATTACHED"
    node.consistency_status = "NEEDS_ATTENTION"


def delete_node(
    session_factory,
    *,
    project_id: str,
    node_id: str | uuid.UUID,
    actor_id: str,
    request_id: str | None,
    expected_version: int,
) -> UserGraphMutationResult:
    session = session_factory()
    try:
        node = get_project_node(
            session,
            project_id=project_id,
            node_id=node_id,
            for_update=True,
            include_deleted=True,
        )
        if node.graph_state == "DELETED":
            session.rollback()
            return UserGraphMutationResult(
                node_id=node.id,
                version=node.version,
                graph_state=node.graph_state,
                changed=False,
            )
        if node.version != expected_version:
            raise NodeVersionConflict(
                str(node.id), expected_version, node.version
            )
        if node.graph_state == "MERGED":
            raise GraphMutationValidationError(
                "MERGED_NODE_DELETE_REQUIRES_UNMERGE"
            )
        if node.graph_state not in {"ACTIVE", "UNATTACHED"}:
            raise GraphMutationValidationError(
                "only ACTIVE or UNATTACHED Nodes can be deleted"
            )
        before = {
            "nodeId": str(node.id),
            "graphState": node.graph_state,
            "version": node.version,
        }
        now = datetime.now(timezone.utc)
        children = _structural_descendants_for_delete(
            session,
            project_id=project_id,
            root_id=node.id,
        )
        if children:
            raise NodeHasChildrenError("NODE_HAS_CHILDREN")
        merged_sources = list(
            session.execute(
                select(Node)
                .where(
                    Node.project_id == project_id,
                    Node.graph_state == "MERGED",
                    Node.merged_into_node_id == node.id,
                    Node.deleted_at.is_(None),
                )
                .order_by(Node.id)
                .with_for_update()
            ).scalars()
        )
        delete_ids = [node.id, *(source.id for source in merged_sources)]
        for relation in session.execute(
            select(Relation).where(
                Relation.project_id == project_id,
                (
                    (Relation.from_node_id.in_(delete_ids))
                    | (Relation.to_node_id.in_(delete_ids))
                ),
                Relation.status == "CONFIRMED",
                Relation.valid_to.is_(None),
            )
        ).scalars():
            relation.status = "REJECTED"
            relation.valid_to = now
        for source in merged_sources:
            source_specs = current_revision_evidence_specs(session, node=source)
            create_node_revision(
                session,
                node=source,
                title=source.title,
                content=source.content,
                node_type=source.node_type,
                category=source.category,
                due_date=source.due_date,
                created_by_type="USER",
                created_by_id=actor_id,
                generation_run_id=None,
                evidence_specs=source_specs,
                requires_evidence=bool(source_specs),
            )
            source.parent_id = None
            source.merged_into_node_id = None
            source.graph_state = "DELETED"
            source.deleted_at = now
            source.deleted_by = actor_id
            source.last_actor_type = "USER"
            mark_node_embedding_stale(session, node=source)
            _event(
                session,
                project_id=project_id,
                node=source,
                actor_id=actor_id,
                request_id=request_id,
                change_type="USER_DELETE_MERGED",
                before={
                    "nodeId": str(source.id),
                    "graphState": "MERGED",
                    "version": source.version - 1,
                },
                detail={"representativeNodeId": str(node.id)},
            )
        root_specs = current_revision_evidence_specs(session, node=node)
        create_node_revision(
            session,
            node=node,
            title=node.title,
            content=node.content,
            node_type=node.node_type,
            category=node.category,
            due_date=node.due_date,
            created_by_type="USER",
            created_by_id=actor_id,
            generation_run_id=None,
            evidence_specs=root_specs,
            requires_evidence=bool(root_specs),
        )
        node.graph_state = "DELETED"
        node.deleted_at = now
        node.deleted_by = actor_id
        node.last_actor_type = "USER"
        mark_node_embedding_stale(session, node=node)
        _event(
            session,
            project_id=project_id,
            node=node,
            actor_id=actor_id,
            request_id=request_id,
            change_type="USER_DELETE_NODE",
            before=before,
        )
        command = session.execute(
            select(MeetingAnalysisCommand).where(
                MeetingAnalysisCommand.project_id == project_id,
                MeetingAnalysisCommand.meeting_id == node.source_meeting_id,
            )
        ).scalar_one_or_none()
        if command is None:
            stage_project_graph_changed(
                session,
                project_id=project_id,
                deleted_nodes=[node, *merged_sources],
            )
        else:
            stage_project_graph_changed_v3(session, command=command)
        session.commit()
        return UserGraphMutationResult(
            node_id=node.id,
            version=node.version,
            graph_state=node.graph_state,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def user_merge_nodes(
    session_factory,
    *,
    project_id: str,
    source_node_id: str | uuid.UUID,
    target_node_id: str | uuid.UUID,
    source_expected_version: int,
    target_expected_version: int,
    actor_id: str,
    reason: str,
) -> UserGraphMutationResult:
    source_id = parse_uuid(source_node_id, field="source_node_id")
    target_id = parse_uuid(target_node_id, field="target_node_id")
    if source_id == target_id:
        raise GraphMutationValidationError("a Node cannot merge into itself")
    session = session_factory()
    try:
        locked = {
            row.id: row
            for row in session.execute(
                select(Node)
                .where(
                    Node.project_id == project_id,
                    Node.id.in_([source_id, target_id]),
                )
                .order_by(Node.id)
                .with_for_update()
            ).scalars()
        }
        if len(locked) != 2:
            raise GraphMutationValidationError(
                "merge Nodes are missing or cross project ownership"
            )
        source = locked[source_id]
        target = locked[target_id]
        if source.version != source_expected_version:
            raise NodeVersionConflict(
                str(source.id), source_expected_version, source.version
            )
        if target.version != target_expected_version:
            raise NodeVersionConflict(
                str(target.id), target_expected_version, target.version
            )
        operation = apply_logical_merge(
            session,
            project_id=project_id,
            source=source,
            target=target,
            actor_type="USER",
            actor_id=actor_id,
            generation_run_id=None,
            reason_code="USER_CONFIRMED_IDENTITY",
            reason_text=reason.strip() or None,
            identity_basis={"userConfirmed": True},
            conflicts_checked={"userConfirmed": {"result": "PASS"}},
            model_confidence=None,
            retrieval_rank=None,
            retrieval_score=None,
            second_retrieval_score=None,
        )
        canonical_target = resolve_canonical_node(
            session,
            project_id=project_id,
            node_id=target.id,
        )
        stage_project_graph_changed(
            session,
            project_id=project_id,
            upserted_nodes=[source, canonical_target],
        )
        session.commit()
        return UserGraphMutationResult(
            node_id=source.id,
            version=source.version,
            graph_state=source.graph_state,
            operation_id=operation.id,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def remerge_operation(
    session_factory,
    *,
    project_id: str,
    operation_id: str | uuid.UUID,
    actor_id: str,
) -> UserGraphMutationResult:
    parsed = parse_uuid(operation_id, field="operation_id")
    session = session_factory()
    try:
        previous = session.execute(
            select(MergeOperation)
            .where(
                MergeOperation.id == parsed,
                MergeOperation.project_id == project_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if previous is None:
            raise GraphMutationValidationError("merge operation not found")
        if previous.status == "APPLIED":
            source = get_project_node(
                session,
                project_id=project_id,
                node_id=previous.source_node_id,
            )
            session.rollback()
            return UserGraphMutationResult(
                node_id=source.id,
                version=source.version,
                graph_state=source.graph_state,
                operation_id=previous.id,
                changed=False,
            )
        source = get_project_node(
            session,
            project_id=project_id,
            node_id=previous.source_node_id,
            for_update=True,
        )
        target = resolve_canonical_node(
            session,
            project_id=project_id,
            node_id=previous.target_node_id,
            expected_node_type=source.node_type,
            for_update=True,
        )
        operation = apply_logical_merge(
            session,
            project_id=project_id,
            source=source,
            target=target,
            actor_type="USER",
            actor_id=actor_id,
            generation_run_id=None,
            reason_code="USER_REMERGE",
            reason_text=f"remerge of {previous.id}",
            identity_basis=previous.identity_basis,
            conflicts_checked=previous.conflicts_checked,
            model_confidence=None,
            retrieval_rank=None,
            retrieval_score=None,
            second_retrieval_score=None,
        )
        stage_project_graph_changed(
            session,
            project_id=project_id,
            upserted_nodes=[source, target],
        )
        session.commit()
        return UserGraphMutationResult(
            node_id=source.id,
            version=source.version,
            graph_state=source.graph_state,
            operation_id=operation.id,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "UserGraphMutationResult",
    "create_user_node",
    "delete_node",
    "edit_node",
    "remerge_operation",
    "unmerge_operation",
    "user_merge_nodes",
]
