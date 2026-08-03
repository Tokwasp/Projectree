"""Read projections and Relation mutation services for the graph API."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from data_pipeline.api.schemas import (
    EvidenceView,
    GenerationRunView,
    GraphNodeListResponse,
    GraphNodeView,
    RelationView,
)
from data_pipeline.pipeline.errors import (
    GraphMutationValidationError,
    NodeVersionConflict,
)
from data_pipeline.pipeline.graph import (
    get_project_node,
    parse_uuid,
    resolve_canonical_node,
)
from data_pipeline.pipeline.event_contract import stage_project_graph_changed
from data_pipeline.pipeline.event_contract import node_snapshot, public_identifier
from data_pipeline.storage import (
    Evidence,
    GenerationRun,
    Node,
    NodeRevisionEvidence,
    OutboxEvent,
    ProjectGraphState,
    Relation,
)


def _evidence_for_canonical(
    session,
    *,
    project_id: str,
    canonical_id: uuid.UUID,
) -> list[EvidenceView]:
    revision_ids: list[uuid.UUID] = []
    for node in session.execute(
        select(Node).where(
            Node.project_id == project_id,
            Node.graph_state.in_(["ACTIVE", "UNATTACHED", "MERGED"]),
            Node.deleted_at.is_(None),
        )
    ).scalars():
        try:
            canonical = resolve_canonical_node(
                session,
                project_id=project_id,
                node_id=node.id,
            )
        except GraphMutationValidationError:
            continue
        if canonical.id == canonical_id and node.current_revision_id is not None:
            revision_ids.append(node.current_revision_id)
    if not revision_ids:
        return []
    rows = session.execute(
        select(NodeRevisionEvidence, Evidence)
        .join(Evidence, Evidence.id == NodeRevisionEvidence.evidence_id)
        .where(
            NodeRevisionEvidence.project_id == project_id,
            NodeRevisionEvidence.node_revision_id.in_(revision_ids),
            Evidence.project_id == project_id,
        )
        .order_by(Evidence.created_at, Evidence.id)
    ).all()
    seen: set[uuid.UUID] = set()
    result: list[EvidenceView] = []
    for _, evidence in rows:
        if evidence.id in seen:
            continue
        seen.add(evidence.id)
        result.append(
            EvidenceView(
                evidenceId=str(evidence.id),
                sourceType=evidence.source_type,
                meetingId=evidence.external_meeting_id,
                segmentId=evidence.source_segment_id,
                speakerLabel=evidence.speaker_label,
                startMs=evidence.start_ms,
                endMs=evidence.end_ms,
                quoteStart=evidence.quote_start,
                quoteEnd=evidence.quote_end,
                quotedText=evidence.quoted_text,
            )
        )
    return result


def _node_view(session, *, node: Node) -> GraphNodeView:
    if node.graph_state == "MERGED":
        canonical = resolve_canonical_node(
            session,
            project_id=node.project_id,
            node_id=node.id,
        )
    else:
        canonical = node
    return GraphNodeView(
        nodeId=str(node.id),
        canonicalNodeId=str(canonical.id),
        projectId=node.project_id,
        nodeType=node.node_type,
        category=node.category,
        title=node.title,
        content=node.content,
        dueDate=node.due_date,
        graphState=node.graph_state,
        consistencyStatus=node.consistency_status,
        parentNodeId=str(node.parent_id) if node.parent_id else None,
        mergedIntoNodeId=(
            str(node.merged_into_node_id)
            if node.merged_into_node_id
            else None
        ),
        originType=node.origin_type,
        version=node.version,
        evidence=_evidence_for_canonical(
            session,
            project_id=node.project_id,
            canonical_id=canonical.id,
        ),
    )


def list_graph_nodes(
    session_factory,
    *,
    project_id: str,
    graph_states: set[str],
) -> GraphNodeListResponse:
    allowed = {
        "ACTIVE",
        "UNATTACHED",
        "MERGED",
        "ARCHIVED",
        "EXCLUDED",
    }
    if not graph_states or not graph_states <= allowed:
        raise GraphMutationValidationError("invalid graphState filter")
    with session_factory() as session:
        nodes = list(
            session.execute(
                select(Node)
                .where(
                    Node.project_id == project_id,
                    Node.graph_state.in_(sorted(graph_states)),
                    Node.deleted_at.is_(None),
                )
                .order_by(Node.created_at, Node.id)
            ).scalars()
        )
        return GraphNodeListResponse(
            total=len(nodes),
            nodes=[_node_view(session, node=node) for node in nodes],
        )


def get_graph_node_view(
    session_factory,
    *,
    project_id: str,
    node_id: str | uuid.UUID,
) -> GraphNodeView:
    with session_factory() as session:
        node = get_project_node(
            session,
            project_id=project_id,
            node_id=node_id,
        )
        return _node_view(session, node=node)


def get_project_graph_snapshot(
    session_factory,
    *,
    project_id: str,
) -> dict | None:
    """Return a deterministic, project-isolated reconciliation snapshot."""

    with session_factory() as session:
        state = session.get(ProjectGraphState, project_id)
        nodes = list(
            session.execute(
                select(Node)
                .where(
                    Node.project_id == project_id,
                    Node.deleted_at.is_(None),
                    Node.graph_state.in_(["ACTIVE", "UNATTACHED", "MERGED"]),
                )
                .order_by(Node.id)
            ).scalars()
        )
        if state is None and not nodes:
            return None
        return {
            "projectId": public_identifier(project_id),
            "graphVersion": state.graph_version if state is not None else 0,
            "nodes": [node_snapshot(session, node) for node in nodes],
        }


def get_generation_run_view(
    session_factory,
    *,
    project_id: str,
    run_id: str | uuid.UUID,
) -> GenerationRunView:
    parsed = parse_uuid(run_id, field="generation_run_id")
    with session_factory() as session:
        run = session.execute(
            select(GenerationRun).where(
                GenerationRun.id == parsed,
                GenerationRun.project_id == project_id,
            )
        ).scalar_one_or_none()
        if run is None:
            raise GraphMutationValidationError("GenerationRun not found")
        return GenerationRunView(
            generationRunId=str(run.id),
            projectId=run.project_id,
            externalMeetingId=run.external_meeting_id,
            status=run.status,
            warnings=run.warnings or [],
            resultSummary=run.result_summary or {},
            failureCode=run.failure_code,
            failureMessage=run.failure_message,
            startedAt=run.started_at,
            completedAt=run.completed_at,
        )


def _relation_view(relation: Relation) -> RelationView:
    return RelationView(
        relationId=str(relation.id),
        fromNodeId=str(relation.from_node_id),
        toNodeId=str(relation.to_node_id),
        relationType=relation.relation_type,
        status=relation.status,
        validFrom=relation.valid_from,
        validTo=relation.valid_to,
    )


def _apply_relation(
    session,
    *,
    project_id: str,
    from_node: Node,
    to_node: Node,
    relation_type: str,
    actor_id: str,
) -> Relation:
    if from_node.id == to_node.id:
        raise GraphMutationValidationError("self relation is not allowed")
    if from_node.graph_state in {"MERGED", "DELETED"}:
        raise GraphMutationValidationError("relation source is not available")
    canonical_target = resolve_canonical_node(
        session,
        project_id=project_id,
        node_id=to_node.id,
        for_update=True,
    )
    if relation_type == "ATTACHED_TO":
        allowed = (
            {"DECISION"}
            if from_node.node_type == "ACTION"
            else {"DECISION", "ACTION"}
            if from_node.node_type == "ISSUE"
            else set()
        )
        if (
            canonical_target.graph_state != "ACTIVE"
            or canonical_target.node_type not in allowed
            or canonical_target.category != from_node.category
            or canonical_target.id == from_node.id
        ):
            raise GraphMutationValidationError(
                "ATTACHED_TO target is not a valid ACTIVE parent"
            )
        ancestor = canonical_target
        visited: set[uuid.UUID] = set()
        while ancestor.parent_id is not None:
            if ancestor.id in visited:
                raise GraphMutationValidationError(
                    "existing parent chain contains a cycle"
                )
            visited.add(ancestor.id)
            ancestor = resolve_canonical_node(
                session,
                project_id=project_id,
                node_id=ancestor.parent_id,
                for_update=True,
            )
            if (
                ancestor.id == from_node.id
                or ancestor.category != from_node.category
            ):
                raise GraphMutationValidationError(
                    "ATTACHED_TO would violate the parent graph boundary"
                )
        for old in session.execute(
            select(Relation).where(
                Relation.project_id == project_id,
                Relation.from_node_id == from_node.id,
                Relation.relation_type == "ATTACHED_TO",
                Relation.status == "CONFIRMED",
                Relation.valid_to.is_(None),
            )
        ).scalars():
            old.status = "REJECTED"
            old.valid_to = datetime.now(timezone.utc)
        from_node.parent_id = canonical_target.id
        from_node.graph_state = "ACTIVE"
        from_node.consistency_status = "NORMAL"
        from_node.version += 1
        from_node.updated_at = datetime.now(timezone.utc)
    from_id, to_id = from_node.id, to_node.id
    if relation_type == "RELATED_TO":
        from_id, to_id = sorted((from_id, to_id), key=str)
    relation = session.execute(
        select(Relation).where(
            Relation.project_id == project_id,
            Relation.from_node_id == from_id,
            Relation.to_node_id == to_id,
            Relation.relation_type == relation_type,
        )
    ).scalar_one_or_none()
    if relation is None:
        relation = Relation(
            project_id=project_id,
            from_node_id=from_id,
            to_node_id=to_id,
            relation_type=relation_type,
            status="CONFIRMED",
            actor_type="USER",
            valid_from=datetime.now(timezone.utc),
        )
        session.add(relation)
    else:
        relation.status = "CONFIRMED"
        relation.actor_type = "USER"
        relation.valid_to = None
        relation.valid_from = datetime.now(timezone.utc)
    session.add(
        OutboxEvent(
            event_type="GRAPH_CHANGED",
            aggregate_type="relation",
            aggregate_id=str(relation.id),
            project_id=project_id,
            schema_version="auto-graph-v1",
            payload={
                "changeType": "USER_UPSERT_RELATION",
                "actorId": actor_id,
                "fromNodeId": str(from_id),
                "toNodeId": str(to_id),
                "relationType": relation_type,
            },
            status="PENDING",
        )
    )
    stage_project_graph_changed(
        session,
        project_id=project_id,
        upserted_nodes=[from_node, canonical_target],
    )
    session.flush()
    return relation


def create_relation(
    session_factory,
    *,
    project_id: str,
    actor_id: str,
    from_node_id: str | uuid.UUID,
    to_node_id: str | uuid.UUID,
    relation_type: str,
    from_expected_version: int,
    to_expected_version: int,
) -> RelationView:
    from_id = parse_uuid(from_node_id, field="from_node_id")
    to_id = parse_uuid(to_node_id, field="to_node_id")
    session = session_factory()
    try:
        locked = {
            node.id: node
            for node in session.execute(
                select(Node)
                .where(
                    Node.project_id == project_id,
                    Node.id.in_([from_id, to_id]),
                    Node.deleted_at.is_(None),
                )
                .order_by(Node.id)
                .with_for_update()
            ).scalars()
        }
        if len(locked) != 2:
            raise GraphMutationValidationError(
                "relation Nodes are missing or cross project ownership"
            )
        from_node, to_node = locked[from_id], locked[to_id]
        if from_node.version != from_expected_version:
            raise NodeVersionConflict(
                str(from_id), from_expected_version, from_node.version
            )
        if to_node.version != to_expected_version:
            raise NodeVersionConflict(
                str(to_id), to_expected_version, to_node.version
            )
        relation = _apply_relation(
            session,
            project_id=project_id,
            from_node=from_node,
            to_node=to_node,
            relation_type=relation_type,
            actor_id=actor_id,
        )
        session.commit()
        return _relation_view(relation)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def replace_relation(
    session_factory,
    *,
    project_id: str,
    actor_id: str,
    relation_id: str | uuid.UUID,
    to_node_id: str | uuid.UUID,
    relation_type: str,
    from_expected_version: int,
    to_expected_version: int,
) -> RelationView:
    parsed_relation = parse_uuid(relation_id, field="relation_id")
    parsed_target = parse_uuid(to_node_id, field="to_node_id")
    session = session_factory()
    try:
        old = session.execute(
            select(Relation)
            .where(
                Relation.id == parsed_relation,
                Relation.project_id == project_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if old is None:
            raise GraphMutationValidationError("relation not found")
        ids = sorted({old.from_node_id, parsed_target}, key=str)
        locked = {
            node.id: node
            for node in session.execute(
                select(Node)
                .where(Node.project_id == project_id, Node.id.in_(ids))
                .where(Node.deleted_at.is_(None))
                .order_by(Node.id)
                .with_for_update()
            ).scalars()
        }
        if len(locked) != len(ids):
            raise GraphMutationValidationError(
                "replacement target is missing or cross project ownership"
            )
        source, target = locked[old.from_node_id], locked[parsed_target]
        if source.version != from_expected_version:
            raise NodeVersionConflict(
                str(source.id), from_expected_version, source.version
            )
        if target.version != to_expected_version:
            raise NodeVersionConflict(
                str(target.id), to_expected_version, target.version
            )
        old.status = "REJECTED"
        old.valid_to = datetime.now(timezone.utc)
        relation = _apply_relation(
            session,
            project_id=project_id,
            from_node=source,
            to_node=target,
            relation_type=relation_type,
            actor_id=actor_id,
        )
        session.commit()
        return _relation_view(relation)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def delete_relation(
    session_factory,
    *,
    project_id: str,
    actor_id: str,
    relation_id: str | uuid.UUID,
) -> RelationView:
    parsed = parse_uuid(relation_id, field="relation_id")
    session = session_factory()
    try:
        relation = session.execute(
            select(Relation)
            .where(Relation.id == parsed, Relation.project_id == project_id)
            .with_for_update()
        ).scalar_one_or_none()
        if relation is None:
            raise GraphMutationValidationError("relation not found")
        if relation.status != "REJECTED" or relation.valid_to is None:
            relation.status = "REJECTED"
            relation.valid_to = datetime.now(timezone.utc)
            if relation.relation_type == "ATTACHED_TO":
                child = get_project_node(
                    session,
                    project_id=project_id,
                    node_id=relation.from_node_id,
                    for_update=True,
                )
                if child.parent_id is not None:
                    child.parent_id = None
                    child.graph_state = "UNATTACHED"
                    child.consistency_status = "NEEDS_ATTENTION"
                    child.version += 1
                    child.updated_at = datetime.now(timezone.utc)
            session.add(
                OutboxEvent(
                    event_type="GRAPH_CHANGED",
                    aggregate_type="relation",
                    aggregate_id=str(relation.id),
                    project_id=project_id,
                    schema_version="auto-graph-v1",
                    payload={
                        "changeType": "USER_DELETE_RELATION",
                        "actorId": actor_id,
                        "relationId": str(relation.id),
                    },
                    status="PENDING",
                )
            )
            changed_nodes: list[Node] = []
            for candidate_id in {relation.from_node_id, relation.to_node_id}:
                candidate = session.execute(
                    select(Node).where(
                        Node.project_id == project_id,
                        Node.id == candidate_id,
                        Node.deleted_at.is_(None),
                    )
                ).scalar_one_or_none()
                if candidate is not None:
                    changed_nodes.append(candidate)
            stage_project_graph_changed(
                session,
                project_id=project_id,
                upserted_nodes=changed_nodes,
            )
        session.commit()
        return _relation_view(relation)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = [
    "create_relation",
    "delete_relation",
    "get_generation_run_view",
    "get_graph_node_view",
    "get_project_graph_snapshot",
    "list_graph_nodes",
    "replace_relation",
]
