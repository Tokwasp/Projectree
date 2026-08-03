"""User approval/rejection of B-model Analysis Candidates."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, text

from data_pipeline.jobs import MANUAL_DECISION_COMPLETED
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
    AnalysisJob,
    GraphChangeEvent,
    Node,
    NodeAnalysisRun,
    NodeEmbedding,
    NodeMergeHistory,
    OutboxEvent,
    Relation,
)

from .analysis import _run_is_current
from .decision_first import release_pending_dependent_nodes_if_ready
from .errors import (
    AnalysisCandidateNotFoundError,
    AnalysisCandidateStateError,
    AnalysisCandidateVersionConflict,
    AnalysisRunNotFoundError,
    NodeNotFoundError,
    NodeStateError,
    NodeValidationError,
    NodeVersionConflict,
)
from .revisions import (
    create_node_revision,
    current_revision_evidence_specs,
    mark_node_embedding_stale,
    reconcile_embedding_status_after_revision,
)


@dataclass(frozen=True)
class UserNodeDecisionResult:
    requested_action: str
    source_node_id: str
    target_node_id: str | None
    relation_id: str | None
    merge_history_id: str | None
    graph_change_event_id: str
    replayed: bool


@dataclass(frozen=True)
class _AppliedDecision:
    relation: Relation | None
    merge_history: NodeMergeHistory | None
    graph_change_event: GraphChangeEvent


def _parse_candidate_id(value: str | uuid.UUID) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise NodeValidationError("candidate_id must be a UUID") from exc


def _parse_uuid(value: str | uuid.UUID, *, field: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise NodeValidationError(f"{field} must be a UUID") from exc


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
    project_id: str,
    request_id: str | None,
    candidate_id: uuid.UUID | None,
    node: Node,
    change_type: str,
    before: dict,
    detail: dict,
) -> GraphChangeEvent:
    audit_detail = dict(detail)
    if candidate_id is not None:
        audit_detail["candidateId"] = str(candidate_id)
    event = GraphChangeEvent(
        project_id=project_id,
        request_id=request_id,
        node_id=node.id,
        item_id=None,
        change_type=change_type,
        actor_type="USER",
        before=before,
        after=_node_snapshot(node),
        detail=audit_detail,
    )
    outbox_payload = {
        "changeType": change_type,
        "nodeId": str(node.id),
    }
    if candidate_id is not None:
        outbox_payload["candidateId"] = str(candidate_id)
    session.add(event)
    session.add(
        OutboxEvent(
            event_type="GRAPH_CHANGED",
            aggregate_type="node",
            aggregate_id=str(node.id),
            project_id=project_id,
            schema_version="v2.2",
            payload=outbox_payload,
            status="PENDING",
        )
    )
    session.flush()
    return event


def _validate_target_shape(
    source: Node,
    target: Node | None,
    action: RecommendationType,
) -> None:
    if action is RecommendationType.CREATE_NEW:
        if target is not None:
            raise NodeValidationError("CREATE_NEW does not accept a target")
        return
    if target is None:
        raise NodeValidationError(f"{action.value} requires a target")
    if target.id == source.id:
        raise AnalysisCandidateStateError(
            f"{action.value} target must not be the source Node"
        )
    if (
        target.graph_state
        not in {GraphState.ACTIVE.value, GraphState.UNATTACHED.value}
        or target.merged_into_node_id is not None
    ):
        raise AnalysisCandidateStateError("target Node is not available")


def _apply_locked_decision(
    session,
    *,
    project_id: str,
    actor_id: str,
    action: RecommendationType,
    source: Node,
    target: Node | None,
    relation_type: str | None,
    merged_title: str | None,
    merged_content: str | None,
    analysis_run_id: uuid.UUID | None,
    candidate_id: uuid.UUID | None,
    audit_request_id: str | None,
    audit_detail: dict,
) -> _AppliedDecision:
    """Apply one already-locked, version-validated graph decision."""

    if (
        source.graph_state != GraphState.UNATTACHED.value
        or source.merged_into_node_id is not None
    ):
        raise AnalysisCandidateStateError(
            "only a non-merged UNATTACHED source Node can be decided"
        )
    _validate_target_shape(source, target, action)

    now = datetime.now(timezone.utc)
    source_before = _node_snapshot(source)
    relation = None
    merge_history = None
    audit_node = source
    audit_before = source_before
    change_type = ""
    detail = dict(audit_detail)

    if action is RecommendationType.CREATE_NEW:
        if relation_type is not None:
            raise NodeValidationError("CREATE_NEW does not accept relation_type")
        if not _can_be_active(session, source):
            raise AnalysisCandidateStateError(
                "Action/Issue requires a valid ATTACHED_TO parent"
            )
        source.graph_state = GraphState.ACTIVE.value
        source.confirmed_by = actor_id
        source.confirmed_at = now
        source.version += 1
        change_type = "CONFIRM_CREATE"
    elif action is RecommendationType.LINK:
        if target is None or relation_type is None:
            raise NodeValidationError("LINK requires target and relation_type")
        if relation_type == RelationType.ATTACHED_TO.value:
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
                or target.category != source.category
                or target.merged_into_node_id is not None
            ):
                raise AnalysisCandidateStateError(
                    "ATTACHED_TO target is not a valid ACTIVE parent"
                )
            relation = _create_relation(
                session,
                project_id=project_id,
                source=source,
                target=target,
                relation_type=relation_type,
            )
            source.parent_id = target.id
        elif relation_type == RelationType.RELATED_TO.value:
            if not _can_be_active(session, source):
                raise AnalysisCandidateStateError(
                    "RELATED_TO does not satisfy the parent requirement"
                )
            relation = _create_relation(
                session,
                project_id=project_id,
                source=source,
                target=target,
                relation_type=relation_type,
            )
        else:
            raise NodeValidationError(f"unsupported relation_type: {relation_type}")
        source.graph_state = GraphState.ACTIVE.value
        source.confirmed_by = actor_id
        source.confirmed_at = now
        source.version += 1
        change_type = "CONFIRM_LINK"
        detail.update(
            {
                "targetNodeId": str(target.id),
                "relationType": relation_type,
                "relationId": str(relation.id),
            }
        )
    elif action is RecommendationType.MERGE:
        if target is None:
            raise NodeValidationError("MERGE requires a target")
        if relation_type is not None:
            raise NodeValidationError("MERGE does not accept relation_type")
        if target.node_type != source.node_type:
            raise AnalysisCandidateStateError(
                "MERGE target must have the same Node type"
            )
        if target.category != source.category:
            # Defense in depth: every Retrieval path scopes category, but an
            # apply transaction must still reject a forged or stale candidate.
            raise AnalysisCandidateStateError(
                "MERGE target must have the same category"
            )
        if target.graph_state != GraphState.ACTIVE.value:
            raise AnalysisCandidateStateError(
                "MERGE target must be an ACTIVE canonical Node"
            )
        if not _can_be_active(session, target):
            raise AnalysisCandidateStateError(
                "merge target cannot satisfy ACTIVE parent rules"
            )
        if merged_title is None or not merged_title.strip():
            raise NodeValidationError("merged_title must not be blank")
        if merged_content is None:
            raise NodeValidationError("merged_content must be provided")
        target_before = _node_snapshot(target)
        source_version = source.version
        target_version = target.version
        target_evidence = current_revision_evidence_specs(session, node=target)
        if target.current_revision_id is None:
            # A legacy projection has no Revision from which the helper can
            # derive the next version. The approved mutation must still advance
            # optimistic concurrency exactly once.
            target.version += 1
        create_node_revision(
            session,
            node=target,
            title=merged_title.strip(),
            content=merged_content,
            node_type=target.node_type,
            category=target.category,
            due_date=target.due_date,
            created_by_type="USER",
            created_by_id=actor_id,
            generation_run_id=None,
            evidence_specs=target_evidence,
            requires_evidence=bool(target_evidence),
            legacy_imported=not bool(target_evidence),
        )
        target.graph_state = GraphState.ACTIVE.value
        target.confirmed_by = actor_id
        target.confirmed_at = now
        source.graph_state = GraphState.MERGED.value
        source.merged_into_node_id = target.id
        source.version += 1
        reconcile_embedding_status_after_revision(session, node=target)
        mark_node_embedding_stale(session, node=source)
        merge_history = NodeMergeHistory(
            project_id=project_id,
            source_node_id=source.id,
            target_node_id=target.id,
            analysis_run_id=analysis_run_id,
            candidate_id=candidate_id,
            approved_by=actor_id,
            approved_at=now,
            source_version=source_version,
            target_version=target_version,
            merged_title=target.title,
            merged_content=target.content,
        )
        session.add(merge_history)
        session.flush()
        audit_node = target
        audit_before = target_before
        change_type = "CONFIRM_MERGE"
        detail.update(
            {
                "sourceNodeId": str(source.id),
                "targetNodeId": str(target.id),
                "mergeHistoryId": str(merge_history.id),
            }
        )
    else:  # pragma: no cover - enum exhaustiveness
        raise NodeValidationError(f"unsupported requested action: {action.value}")

    if source.node_type == NodeType.DECISION.value:
        released = release_pending_dependent_nodes_if_ready(
            session,
            project_id=project_id,
            meeting_id=source.source_meeting_id,
        )
        detail.update(
            {
                "decisionFirstPhase": released.phase,
                "releasedDependentNodeCount": released.queued_count,
                "releasedDependentNodeIds": [
                    str(node_id) for node_id in released.queued_node_ids
                ],
            }
        )

    event = _audit(
        session,
        project_id=project_id,
        request_id=audit_request_id,
        candidate_id=candidate_id,
        node=audit_node,
        change_type=change_type,
        before=audit_before,
        detail=detail,
    )
    return _AppliedDecision(
        relation=relation,
        merge_history=merge_history,
        graph_change_event=event,
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
        action = RecommendationType(candidate.recommendation)
        final_title = merged_title
        final_content = merged_content
        if action is RecommendationType.MERGE:
            final_title = final_title or candidate.suggested_title
            if final_content is None:
                final_content = candidate.suggested_content
        applied = _apply_locked_decision(
            session,
            project_id=project_id,
            actor_id=actor_id.strip(),
            action=action,
            source=source,
            target=target,
            relation_type=candidate.relation_type,
            merged_title=final_title,
            merged_content=final_content,
            analysis_run_id=run.id,
            candidate_id=candidate.id,
            audit_request_id=str(run.id),
            audit_detail={
                "decisionOrigin": "RECOMMENDATION_APPROVAL",
                "recommendedAction": candidate.recommendation,
                "requestedAction": candidate.recommendation,
            },
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
            relation_id=(
                str(applied.relation.id) if applied.relation else None
            ),
            merge_history_id=(
                str(applied.merge_history.id)
                if applied.merge_history
                else None
            ),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _decision_request_key(
    *,
    project_id: str,
    source_node_id: uuid.UUID,
    requested_action: RecommendationType,
    source_expected_version: int,
    target_node_id: uuid.UUID | None,
    target_expected_version: int | None,
    relation_type: str | None,
    analysis_run_id: uuid.UUID | None,
    recommendation_id: uuid.UUID | None,
    merged_title: str | None,
    merged_content: str | None,
) -> str:
    payload = [
        "manual-node-decision-v1",
        project_id,
        str(source_node_id),
        requested_action.value,
        source_expected_version,
        str(target_node_id) if target_node_id else None,
        target_expected_version,
        relation_type,
        str(analysis_run_id) if analysis_run_id else None,
        str(recommendation_id) if recommendation_id else None,
        merged_title,
        merged_content,
    ]
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _manual_result_from_event(
    event: GraphChangeEvent,
    *,
    requested_action: RecommendationType,
    replayed: bool,
) -> UserNodeDecisionResult:
    detail = event.detail or {}
    return UserNodeDecisionResult(
        requested_action=requested_action.value,
        source_node_id=str(detail["decisionSourceNodeId"]),
        target_node_id=detail.get("targetNodeId"),
        relation_id=detail.get("relationId"),
        merge_history_id=detail.get("mergeHistoryId"),
        graph_change_event_id=str(event.id),
        replayed=replayed,
    )


def _manual_reference_context(
    session,
    *,
    project_id: str,
    source: Node,
    analysis_run_id: uuid.UUID | None,
    recommendation_id: uuid.UUID | None,
) -> tuple[NodeAnalysisRun | None, AnalysisCandidate | None]:
    recommendation = None
    if recommendation_id is not None:
        recommendation = session.execute(
            select(AnalysisCandidate)
            .where(
                AnalysisCandidate.id == recommendation_id,
                AnalysisCandidate.project_id == project_id,
                AnalysisCandidate.source_node_id == source.id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if recommendation is None:
            raise AnalysisCandidateNotFoundError(
                f"analysis candidate not found: {recommendation_id}"
            )
        if recommendation.status == AnalysisCandidateStatus.APPROVED.value:
            raise AnalysisCandidateStateError(
                "an already approved recommendation cannot be overridden"
            )
        if recommendation.source_node_version != source.version:
            raise AnalysisCandidateStateError(
                "recommendation no longer matches the source Node version"
            )
        if recommendation.target_node_id is not None:
            recommended_target = session.execute(
                select(Node).where(
                    Node.id == recommendation.target_node_id,
                    Node.project_id == project_id,
                )
            ).scalar_one_or_none()
            if (
                recommended_target is None
                or recommended_target.version
                != recommendation.target_node_version
                or recommended_target.graph_state
                not in {GraphState.ACTIVE.value, GraphState.UNATTACHED.value}
                or recommended_target.merged_into_node_id is not None
            ):
                raise AnalysisCandidateStateError(
                    "recommendation target is stale"
                )
        if (
            analysis_run_id is not None
            and analysis_run_id != recommendation.analysis_run_id
        ):
            raise AnalysisCandidateStateError(
                "analysisRunId and recommendationId do not refer to the same run"
            )
        analysis_run_id = recommendation.analysis_run_id

    run = None
    if analysis_run_id is not None:
        run = session.execute(
            select(NodeAnalysisRun)
            .join(Node, Node.id == NodeAnalysisRun.source_node_id)
            .where(
                NodeAnalysisRun.id == analysis_run_id,
                NodeAnalysisRun.source_node_id == source.id,
                Node.project_id == project_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            raise AnalysisRunNotFoundError(
                f"analysis run not found: {analysis_run_id}"
            )
        if (
            run.source_node_version != source.version
            or source.current_analysis_run_id != run.id
            or run.status == AnalysisRunStatus.SUPERSEDED.value
        ):
            raise AnalysisCandidateStateError(
                "analysis Run no longer matches the current source Node"
            )
    return run, recommendation


def _close_source_review_state(
    session,
    *,
    source: Node,
    actor_id: str,
    referenced_run: NodeAnalysisRun | None,
) -> None:
    now = datetime.now(timezone.utc)
    pending_candidates = session.execute(
        select(AnalysisCandidate)
        .where(
            AnalysisCandidate.source_node_id == source.id,
            AnalysisCandidate.status == AnalysisCandidateStatus.PENDING.value,
        )
        .with_for_update()
    ).scalars().all()
    for candidate in pending_candidates:
        candidate.status = AnalysisCandidateStatus.REJECTED.value
        candidate.version += 1
        candidate.decided_by = actor_id
        candidate.decided_at = now
        candidate.updated_at = now

    run_to_close = referenced_run
    if run_to_close is None and source.current_analysis_run_id is not None:
        run_to_close = session.execute(
            select(NodeAnalysisRun)
            .where(
                NodeAnalysisRun.id == source.current_analysis_run_id,
                NodeAnalysisRun.source_node_id == source.id,
            )
            .with_for_update()
        ).scalar_one_or_none()
    if (
        run_to_close is not None
        and run_to_close.status
        in {
            AnalysisRunStatus.PENDING.value,
            AnalysisRunStatus.RUNNING.value,
        }
    ):
        run_to_close.status = AnalysisRunStatus.SUPERSEDED.value
        run_to_close.completed_at = now
        run_to_close.updated_at = now

    jobs = session.execute(
        select(AnalysisJob)
        .where(
            AnalysisJob.node_id == source.id,
            AnalysisJob.status.in_(("PENDING", "RUNNING")),
        )
        .with_for_update()
    ).scalars().all()
    for job in jobs:
        job.status = "FAILED"
        job.claim_token = None
        job.failure_code = MANUAL_DECISION_COMPLETED
        job.last_error = "analysis stopped after a user final decision"
        job.updated_at = now


def decide_node(
    session_factory,
    source_node_id: str | uuid.UUID,
    *,
    project_id: str,
    actor_id: str,
    requested_action: str | RecommendationType,
    source_expected_version: int,
    target_node_id: str | uuid.UUID | None = None,
    target_expected_version: int | None = None,
    relation_type: str | RelationType | None = None,
    analysis_run_id: str | uuid.UUID | None = None,
    recommendation_id: str | uuid.UUID | None = None,
    merged_title: str | None = None,
    merged_content: str | None = None,
) -> UserNodeDecisionResult:
    """Apply a user's final decision without requiring a model recommendation."""

    if not actor_id or not actor_id.strip():
        raise NodeValidationError("actor_id must not be empty")
    try:
        action = (
            requested_action
            if isinstance(requested_action, RecommendationType)
            else RecommendationType(str(requested_action))
        )
    except ValueError as exc:
        raise NodeValidationError(
            f"unsupported requested_action: {requested_action}"
        ) from exc
    parsed_source_id = _parse_uuid(source_node_id, field="source_node_id")
    parsed_target_id = (
        _parse_uuid(target_node_id, field="target_node_id")
        if target_node_id is not None
        else None
    )
    parsed_run_id = (
        _parse_uuid(analysis_run_id, field="analysis_run_id")
        if analysis_run_id is not None
        else None
    )
    parsed_recommendation_id = (
        _parse_uuid(recommendation_id, field="recommendation_id")
        if recommendation_id is not None
        else None
    )
    normalized_relation = (
        relation_type.value
        if isinstance(relation_type, RelationType)
        else (str(relation_type) if relation_type is not None else None)
    )
    if action is RecommendationType.CREATE_NEW:
        if (
            parsed_target_id is not None
            or target_expected_version is not None
            or normalized_relation is not None
        ):
            raise NodeValidationError(
                "CREATE_NEW does not accept target or relation fields"
            )
    elif action is RecommendationType.LINK:
        if (
            parsed_target_id is None
            or target_expected_version is None
            or normalized_relation
            not in {
                RelationType.ATTACHED_TO.value,
                RelationType.RELATED_TO.value,
            }
        ):
            raise NodeValidationError(
                "LINK requires target, target version, and a valid relation type"
            )
    elif (
        parsed_target_id is None
        or target_expected_version is None
        or normalized_relation is not None
    ):
        raise NodeValidationError(
            "MERGE requires target and target version without relation type"
        )

    request_key = _decision_request_key(
        project_id=project_id,
        source_node_id=parsed_source_id,
        requested_action=action,
        source_expected_version=source_expected_version,
        target_node_id=parsed_target_id,
        target_expected_version=target_expected_version,
        relation_type=normalized_relation,
        analysis_run_id=parsed_run_id,
        recommendation_id=parsed_recommendation_id,
        merged_title=merged_title,
        merged_content=merged_content,
    )
    audit_request_id = f"manual:{request_key}"
    session = session_factory()
    try:
        if session.get_bind().dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        source = session.execute(
            select(Node)
            .where(
                Node.id == parsed_source_id,
                Node.project_id == project_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if source is None:
            raise NodeNotFoundError(f"node not found: {source_node_id}")

        existing_event = session.execute(
            select(GraphChangeEvent).where(
                GraphChangeEvent.project_id == project_id,
                GraphChangeEvent.request_id == audit_request_id,
            )
        ).scalar_one_or_none()
        if existing_event is not None:
            result = _manual_result_from_event(
                existing_event,
                requested_action=action,
                replayed=True,
            )
            session.rollback()
            return result

        if source.version != source_expected_version:
            raise NodeVersionConflict(
                str(source.id),
                source_expected_version,
                source.version,
            )
        if (
            source.graph_state != GraphState.UNATTACHED.value
            or source.merged_into_node_id is not None
        ):
            raise NodeStateError(
                "only a non-merged UNATTACHED source Node can be decided"
            )

        run, recommendation = _manual_reference_context(
            session,
            project_id=project_id,
            source=source,
            analysis_run_id=parsed_run_id,
            recommendation_id=parsed_recommendation_id,
        )
        if run is not None:
            parsed_run_id = run.id

        target = None
        if parsed_target_id is not None:
            target = session.execute(
                select(Node)
                .where(
                    Node.id == parsed_target_id,
                    Node.project_id == project_id,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if target is None:
                raise NodeNotFoundError(f"node not found: {target_node_id}")
            if target.version != target_expected_version:
                raise NodeVersionConflict(
                    str(target.id),
                    target_expected_version,
                    target.version,
                )

        recommended_action = (
            recommendation.recommendation if recommendation is not None else None
        )
        applied = _apply_locked_decision(
            session,
            project_id=project_id,
            actor_id=actor_id.strip(),
            action=action,
            source=source,
            target=target,
            relation_type=normalized_relation,
            merged_title=merged_title,
            merged_content=merged_content,
            analysis_run_id=parsed_run_id,
            candidate_id=parsed_recommendation_id,
            audit_request_id=audit_request_id,
            audit_detail={
                "decisionOrigin": "MANUAL",
                "decisionRequestKey": request_key,
                "decisionSourceNodeId": str(source.id),
                "requestedAction": action.value,
                "recommendedAction": recommended_action,
                "recommendationId": (
                    str(parsed_recommendation_id)
                    if parsed_recommendation_id
                    else None
                ),
                "analysisRunId": str(parsed_run_id) if parsed_run_id else None,
            },
        )
        _close_source_review_state(
            session,
            source=source,
            actor_id=actor_id.strip(),
            referenced_run=run,
        )
        session.flush()
        session.commit()
        return _manual_result_from_event(
            applied.graph_change_event,
            requested_action=action,
            replayed=False,
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
    merged_title: str | None = None,
    merged_content: str | None = None,
) -> AnalysisCandidateDecisionResult:
    return approve_analysis_candidate(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=expected_version,
        merged_title=merged_title,
        merged_content=merged_content,
        _required_recommendation=RecommendationType.MERGE,
    )


__all__ = [
    "UserNodeDecisionResult",
    "approve_analysis_candidate",
    "approve_create_new",
    "approve_link_existing",
    "approve_merge_existing",
    "decide_node",
    "reject_analysis_candidate",
]
