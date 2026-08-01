"""User approval/rejection of B-model Analysis Candidates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text, update

from data_pipeline.contracts import (
    AnalysisCandidateDecisionResult,
    AnalysisCandidateStatus,
    AnalysisCandidateView,
    AnalysisRunStatus,
    GraphState,
    NodeType,
    RecommendationType,
    RelationStatus,
    RelationType,
)
from data_pipeline.storage import (
    AnalysisCandidate,
    GraphChangeEvent,
    Node,
    NodeAnalysisRun,
    NodeEmbedding,
    NodeMergeHistory,
    OutboxEvent,
    Relation,
)

from .analysis import _run_is_current
from .errors import (
    AnalysisCandidateNotFoundError,
    AnalysisCandidateStateError,
    AnalysisCandidateVersionConflict,
    NodeStateError,
    NodeValidationError,
)


def _parse_candidate_id(value: str | uuid.UUID) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise NodeValidationError("candidate_id must be a UUID") from exc


def _candidate_view(candidate: AnalysisCandidate) -> AnalysisCandidateView:
    return AnalysisCandidateView(
        candidate_id=str(candidate.id),
        analysis_run_id=str(candidate.analysis_run_id),
        source_node_id=str(candidate.source_node_id),
        target_node_id=(
            str(candidate.target_node_id)
            if candidate.target_node_id is not None
            else None
        ),
        recommendation=RecommendationType(candidate.recommendation),
        relation_type=candidate.relation_type,
        suggested_title=candidate.suggested_title,
        suggested_content=candidate.suggested_content,
        reason=candidate.reason,
        status=AnalysisCandidateStatus(candidate.status),
        version=candidate.version,
        decided_by=candidate.decided_by,
        decided_at=candidate.decided_at,
    )


def _locked_candidate(session, candidate_id: uuid.UUID, project_id: str):
    if session.get_bind().dialect.name == "sqlite":
        # SQLite ignores SELECT ... FOR UPDATE. Acquire its database write
        # lock before reading the decision version so approve/reject cannot
        # both observe the same PENDING candidate and overwrite each other.
        session.execute(text("BEGIN IMMEDIATE"))
    candidate = session.execute(
        select(AnalysisCandidate)
        .where(
            AnalysisCandidate.id == candidate_id,
            AnalysisCandidate.project_id == project_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    if candidate is None:
        raise AnalysisCandidateNotFoundError(
            f"analysis candidate not found: {candidate_id}"
        )
    return candidate


def _locked_node(session, node_id: uuid.UUID, project_id: str) -> Node:
    node = session.execute(
        select(Node)
        .where(Node.id == node_id, Node.project_id == project_id)
        .with_for_update()
    ).scalar_one_or_none()
    if node is None:
        raise NodeStateError(f"Node is not available: {node_id}")
    return node


def _confirmed_parent(session, node: Node) -> Node | None:
    if node.parent_id is None:
        return None
    parent = session.execute(
        select(Node).where(
            Node.id == node.parent_id,
            Node.project_id == node.project_id,
            Node.graph_state == GraphState.ACTIVE.value,
            Node.merged_into_node_id.is_(None),
        )
    ).scalar_one_or_none()
    if parent is None:
        return None
    relation = session.execute(
        select(Relation.id).where(
            Relation.project_id == node.project_id,
            Relation.from_node_id == node.id,
            Relation.to_node_id == parent.id,
            Relation.relation_type == RelationType.ATTACHED_TO.value,
            Relation.status == RelationStatus.CONFIRMED.value,
        )
    ).scalar_one_or_none()
    if relation is None:
        return None
    allowed = {
        NodeType.ACTION.value: {NodeType.DECISION.value},
        NodeType.ISSUE.value: {
            NodeType.DECISION.value,
            NodeType.ACTION.value,
        },
    }.get(node.node_type, set())
    return parent if parent.node_type in allowed else None


def _can_be_active(session, node: Node) -> bool:
    if node.node_type == NodeType.DECISION.value:
        return True
    return _confirmed_parent(session, node) is not None


def _relation_pair(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    relation_type: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    if relation_type == RelationType.RELATED_TO.value:
        return tuple(
            sorted((source_id, target_id), key=str)
        )
    return source_id, target_id


def _create_relation(
    session,
    *,
    project_id: str,
    source: Node,
    target: Node,
    relation_type: str,
) -> Relation:
    from_id, to_id = _relation_pair(source.id, target.id, relation_type)
    existing = session.execute(
        select(Relation).where(
            Relation.project_id == project_id,
            Relation.from_node_id == from_id,
            Relation.to_node_id == to_id,
            Relation.relation_type == relation_type,
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.status != RelationStatus.CONFIRMED.value:
            existing.status = RelationStatus.CONFIRMED.value
            existing.actor_type = "USER"
        return existing
    relation = Relation(
        project_id=project_id,
        from_node_id=from_id,
        to_node_id=to_id,
        relation_type=relation_type,
        status=RelationStatus.CONFIRMED.value,
        actor_type="USER",
    )
    session.add(relation)
    session.flush()
    return relation


def _stale_embeddings(session, node_id: uuid.UUID) -> None:
    session.execute(
        update(NodeEmbedding)
        .where(
            NodeEmbedding.node_id == node_id,
            NodeEmbedding.status == "READY",
        )
        .values(status="STALE")
    )


def _node_snapshot(node: Node) -> dict:
    return {
        "nodeId": str(node.id),
        "graphState": node.graph_state,
        "parentId": str(node.parent_id) if node.parent_id else None,
        "mergedIntoNodeId": (
            str(node.merged_into_node_id)
            if node.merged_into_node_id
            else None
        ),
        "title": node.title,
        "content": node.content,
        "version": node.version,
    }


def _audit(
    session,
    *,
    candidate: AnalysisCandidate,
    node: Node,
    change_type: str,
    before: dict,
    detail: dict,
) -> None:
    session.add(
        GraphChangeEvent(
            project_id=candidate.project_id,
            request_id=str(candidate.analysis_run_id),
            node_id=node.id,
            item_id=None,
            change_type=change_type,
            actor_type="USER",
            before=before,
            after=_node_snapshot(node),
            detail={"candidateId": str(candidate.id), **detail},
        )
    )
    session.add(
        OutboxEvent(
            event_type="GRAPH_CHANGED",
            aggregate_type="node",
            aggregate_id=str(node.id),
            project_id=candidate.project_id,
            schema_version="v2.2",
            payload={
                "candidateId": str(candidate.id),
                "changeType": change_type,
                "nodeId": str(node.id),
            },
            status="PENDING",
        )
    )


def reject_analysis_candidate(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    project_id: str,
    actor_id: str,
    expected_version: int,
) -> AnalysisCandidateDecisionResult:
    if not actor_id.strip():
        raise NodeValidationError("actor_id must not be empty")
    parsed_id = _parse_candidate_id(candidate_id)
    session = session_factory()
    try:
        candidate = _locked_candidate(session, parsed_id, project_id)
        if candidate.status == AnalysisCandidateStatus.REJECTED.value:
            result = AnalysisCandidateDecisionResult(
                candidate=_candidate_view(candidate),
                source_node_id=str(candidate.source_node_id),
                target_node_id=(
                    str(candidate.target_node_id)
                    if candidate.target_node_id
                    else None
                ),
            )
            session.rollback()
            return result
        if candidate.status != AnalysisCandidateStatus.PENDING.value:
            raise AnalysisCandidateStateError(
                "an approved Candidate cannot be rejected"
            )
        if candidate.version != expected_version:
            raise AnalysisCandidateVersionConflict(
                str(candidate.id),
                expected_version,
                candidate.version,
            )
        now = datetime.now(timezone.utc)
        candidate.status = AnalysisCandidateStatus.REJECTED.value
        candidate.version += 1
        candidate.decided_by = actor_id.strip()
        candidate.decided_at = now
        candidate.updated_at = now
        session.commit()
        return AnalysisCandidateDecisionResult(
            candidate=_candidate_view(candidate),
            source_node_id=str(candidate.source_node_id),
            target_node_id=(
                str(candidate.target_node_id)
                if candidate.target_node_id
                else None
            ),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def approve_analysis_candidate(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    project_id: str,
    actor_id: str,
    expected_version: int,
    confirm_unattached_target: bool = False,
    merged_title: str | None = None,
    merged_content: str | None = None,
    _required_recommendation: RecommendationType | None = None,
) -> AnalysisCandidateDecisionResult:
    """Apply CREATE_NEW/LINK/MERGE exactly once in one transaction."""

    if not actor_id.strip():
        raise NodeValidationError("actor_id must not be empty")
    parsed_id = _parse_candidate_id(candidate_id)
    session = session_factory()
    try:
        candidate = _locked_candidate(session, parsed_id, project_id)
        if (
            _required_recommendation is not None
            and candidate.recommendation
            != _required_recommendation.value
        ):
            raise AnalysisCandidateStateError(
                "Candidate recommendation does not match this approval path"
            )
        if candidate.status == AnalysisCandidateStatus.APPROVED.value:
            merge_history = session.execute(
                select(NodeMergeHistory).where(
                    NodeMergeHistory.candidate_id == candidate.id
                )
            ).scalar_one_or_none()
            relation = None
            if candidate.recommendation == RecommendationType.LINK.value:
                from_id, to_id = _relation_pair(
                    candidate.source_node_id,
                    candidate.target_node_id,
                    candidate.relation_type,
                )
                relation = session.execute(
                    select(Relation).where(
                        Relation.project_id == project_id,
                        Relation.from_node_id == from_id,
                        Relation.to_node_id == to_id,
                        Relation.relation_type == candidate.relation_type,
                    )
                ).scalar_one_or_none()
            result = AnalysisCandidateDecisionResult(
                candidate=_candidate_view(candidate),
                source_node_id=str(candidate.source_node_id),
                target_node_id=(
                    str(candidate.target_node_id)
                    if candidate.target_node_id
                    else None
                ),
                relation_id=str(relation.id) if relation else None,
                merge_history_id=(
                    str(merge_history.id) if merge_history else None
                ),
            )
            session.rollback()
            return result
        if candidate.status != AnalysisCandidateStatus.PENDING.value:
            raise AnalysisCandidateStateError(
                "a rejected Candidate cannot be approved"
            )
        if candidate.version != expected_version:
            raise AnalysisCandidateVersionConflict(
                str(candidate.id),
                expected_version,
                candidate.version,
            )
        source = _locked_node(
            session,
            candidate.source_node_id,
            project_id,
        )
        run = session.execute(
            select(NodeAnalysisRun)
            .where(
                NodeAnalysisRun.id == candidate.analysis_run_id,
                NodeAnalysisRun.source_node_id == source.id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if (
            run is None
            or run.status != AnalysisRunStatus.COMPLETED.value
            or not _run_is_current(run, source)
            or source.version != candidate.source_node_version
            or source.graph_state != GraphState.UNATTACHED.value
        ):
            raise AnalysisCandidateStateError(
                "Candidate no longer matches the current source Node"
            )

        target = None
        if candidate.target_node_id is not None:
            target = _locked_node(
                session,
                candidate.target_node_id,
                project_id,
            )
            if (
                target.id == source.id
                or target.version != candidate.target_node_version
                or target.graph_state
                not in {GraphState.ACTIVE.value, GraphState.UNATTACHED.value}
                or target.merged_into_node_id is not None
            ):
                raise AnalysisCandidateStateError(
                    "Candidate target is no longer valid"
                )

        now = datetime.now(timezone.utc)
        source_before = _node_snapshot(source)
        relation = None
        merge_history = None
        if candidate.recommendation == RecommendationType.CREATE_NEW.value:
            if not _can_be_active(session, source):
                raise AnalysisCandidateStateError(
                    "Action/Issue requires a valid ATTACHED_TO parent"
                )
            source.graph_state = GraphState.ACTIVE.value
            source.confirmed_by = actor_id.strip()
            source.confirmed_at = now
            source.version += 1
            _audit(
                session,
                candidate=candidate,
                node=source,
                change_type="CONFIRM_CREATE",
                before=source_before,
                detail={},
            )
        elif candidate.recommendation == RecommendationType.LINK.value:
            if target is None or candidate.relation_type is None:
                raise AnalysisCandidateStateError(
                    "LINK Candidate has no target or relation type"
                )
            if candidate.relation_type == RelationType.ATTACHED_TO.value:
                allowed = {
                    NodeType.ACTION.value: {NodeType.DECISION.value},
                    NodeType.ISSUE.value: {
                        NodeType.DECISION.value,
                        NodeType.ACTION.value,
                    },
                }.get(source.node_type, set())
                if (
                    target.graph_state != GraphState.ACTIVE.value
                    or target.node_type not in allowed
                ):
                    raise AnalysisCandidateStateError(
                        "ATTACHED_TO target is not a valid ACTIVE parent"
                    )
                relation = _create_relation(
                    session,
                    project_id=project_id,
                    source=source,
                    target=target,
                    relation_type=candidate.relation_type,
                )
                source.parent_id = target.id
            elif not _can_be_active(session, source):
                raise AnalysisCandidateStateError(
                    "RELATED_TO does not satisfy the parent requirement"
                )
            else:
                relation = _create_relation(
                    session,
                    project_id=project_id,
                    source=source,
                    target=target,
                    relation_type=candidate.relation_type,
                )
            source.graph_state = GraphState.ACTIVE.value
            source.confirmed_by = actor_id.strip()
            source.confirmed_at = now
            source.version += 1
            _audit(
                session,
                candidate=candidate,
                node=source,
                change_type="CONFIRM_LINK",
                before=source_before,
                detail={
                    "targetNodeId": str(target.id),
                    "relationType": candidate.relation_type,
                },
            )
        elif candidate.recommendation == RecommendationType.MERGE.value:
            if target is None:
                raise AnalysisCandidateStateError(
                    "MERGE Candidate has no target"
                )
            if target.node_type != source.node_type:
                raise AnalysisCandidateStateError(
                    "MERGE target must have the same Node type"
                )
            if (
                target.graph_state == GraphState.UNATTACHED.value
                and not confirm_unattached_target
            ):
                raise AnalysisCandidateStateError(
                    "UNATTACHED merge target requires explicit confirmation"
                )
            if not _can_be_active(session, target):
                raise AnalysisCandidateStateError(
                    "merge target cannot satisfy ACTIVE parent rules"
                )
            final_title = (
                merged_title
                if merged_title is not None
                else candidate.suggested_title
            )
            final_content = (
                merged_content
                if merged_content is not None
                else candidate.suggested_content
            )
            if not final_title.strip():
                raise NodeValidationError("merged_title must not be blank")
            target_before = _node_snapshot(target)
            source_version = source.version
            target_version = target.version
            target.title = final_title.strip()
            target.content = final_content
            target.graph_state = GraphState.ACTIVE.value
            target.confirmed_by = actor_id.strip()
            target.confirmed_at = now
            target.version += 1
            source.graph_state = GraphState.MERGED.value
            source.merged_into_node_id = target.id
            source.version += 1
            _stale_embeddings(session, target.id)
            merge_history = NodeMergeHistory(
                project_id=project_id,
                source_node_id=source.id,
                target_node_id=target.id,
                analysis_run_id=run.id,
                candidate_id=candidate.id,
                approved_by=actor_id.strip(),
                approved_at=now,
                source_version=source_version,
                target_version=target_version,
                merged_title=target.title,
                merged_content=target.content,
            )
            session.add(merge_history)
            session.flush()
            _audit(
                session,
                candidate=candidate,
                node=target,
                change_type="CONFIRM_MERGE",
                before=target_before,
                detail={"sourceNodeId": str(source.id)},
            )
        else:
            raise AnalysisCandidateStateError(
                f"unsupported recommendation: {candidate.recommendation}"
            )

        candidate.status = AnalysisCandidateStatus.APPROVED.value
        candidate.version += 1
        candidate.decided_by = actor_id.strip()
        candidate.decided_at = now
        candidate.updated_at = now
        session.flush()
        session.commit()
        return AnalysisCandidateDecisionResult(
            candidate=_candidate_view(candidate),
            source_node_id=str(source.id),
            target_node_id=str(target.id) if target else None,
            relation_id=str(relation.id) if relation else None,
            merge_history_id=(
                str(merge_history.id) if merge_history else None
            ),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def approve_create_new(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    project_id: str,
    actor_id: str,
    expected_version: int,
) -> AnalysisCandidateDecisionResult:
    return approve_analysis_candidate(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=expected_version,
        _required_recommendation=RecommendationType.CREATE_NEW,
    )


def approve_link_existing(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    project_id: str,
    actor_id: str,
    expected_version: int,
) -> AnalysisCandidateDecisionResult:
    return approve_analysis_candidate(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=expected_version,
        _required_recommendation=RecommendationType.LINK,
    )


def approve_merge_existing(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    project_id: str,
    actor_id: str,
    expected_version: int,
    confirm_unattached_target: bool = False,
    merged_title: str | None = None,
    merged_content: str | None = None,
) -> AnalysisCandidateDecisionResult:
    return approve_analysis_candidate(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=expected_version,
        confirm_unattached_target=confirm_unattached_target,
        merged_title=merged_title,
        merged_content=merged_content,
        _required_recommendation=RecommendationType.MERGE,
    )


__all__ = [
    "approve_analysis_candidate",
    "approve_create_new",
    "approve_link_existing",
    "approve_merge_existing",
    "reject_analysis_candidate",
]
