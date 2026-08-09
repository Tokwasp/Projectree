"""Decision-first automatic graph planning and atomic publication.

All external Embedding/B-model calls happen while only ``GenerationRun`` state
is durable. Nodes, revisions, evidence, relations, logical merges, analysis
artifacts, and the completion outbox are published in one short transaction.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from data_pipeline.b_model import (
    BModelClient,
    describe_b_model_failure,
    sanitize_text,
)
from data_pipeline.config import RetrievalSettings, load_settings
from data_pipeline.contracts import (
    BModelDecision,
    RecommendationType,
    allowed_parent_types,
)
from data_pipeline.retrieval import (
    EmbeddingClient,
    RetrievedNode,
    build_embedding_text_from_parts,
    search_link_candidates,
    search_merge_candidates,
    validate_embedding,
)
from data_pipeline.storage import (
    BModelResult,
    Category,
    GenerationRun,
    Meeting,
    MeetingAnalysisCommand,
    Node,
    NodeAnalysisRun,
    NodeCandidate,
    NodeEmbedding,
    NodeRevision,
    OutboxEvent,
    Relation,
    Request,
    RetrievalResult,
)

from .errors import (
    GenerationRunStateError,
    GraphIntegrityError,
    GraphMutationValidationError,
)
from .graph import apply_logical_merge, resolve_canonical_node
from .event_contract import (
    canonical_storage_identifier,
    mark_graph_ready,
    stage_analysis_failed,
    stage_analysis_processing,
    stage_project_graph_changed,
)
from .revisions import (
    EvidenceSpec,
    create_node_revision,
    current_revision_evidence_specs,
    evidence_hash,
    mark_node_embedding_stale,
    reconcile_embedding_status_after_revision,
    validated_candidate_evidence,
)

logger = logging.getLogger(__name__)

_NODE_TYPES = {"DECISION", "ACTION", "ISSUE"}
_PUBLISHED_STATES = {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
_MERGE_ACTION_PARENT_CONFLICT = "MERGE_ACTION_PARENT_CONFLICT"
_MERGE_ACTION_INTENDED_PARENT_MISSING = (
    "MERGE_ACTION_INTENDED_PARENT_MISSING"
)
_MERGE_ACTION_INTENDED_PARENT_INVALID = (
    "MERGE_ACTION_INTENDED_PARENT_INVALID"
)
_MERGE_ACTION_TARGET_PARENT_MISSING = "MERGE_ACTION_TARGET_PARENT_MISSING"
_MERGE_ACTION_TARGET_PARENT_INVALID = "MERGE_ACTION_TARGET_PARENT_INVALID"


@dataclass(frozen=True)
class AutoMergePolicy:
    """Calibrated server gate. ``None`` means automatic MERGE is disabled."""

    min_similarity: float | None = None
    min_margin: float | None = None


@dataclass(frozen=True)
class CandidateSnapshot:
    candidate_id: uuid.UUID
    source_item_id: str
    project_id: str
    external_meeting_id: str
    node_id: uuid.UUID
    node_type: str
    category: str
    title: str
    content: str
    due_date: str | None
    suggested_parent_candidate_id: uuid.UUID | None
    evidence: tuple[EvidenceSpec, ...]


@dataclass(frozen=True)
class RetrievalSnapshot:
    target_node_id: uuid.UUID
    target_node_version: int
    rank: int
    similarity: float
    node_type: str
    category: str
    title: str
    content: str
    graph_state: str
    parent_id: uuid.UUID | None
    due_date: str | None


@dataclass(frozen=True)
class BModelFailure:
    """A B-model call that started but did not produce a usable decision.

    Distinct from a skip: a skip means the call was never attempted. Only a
    failure carries a code/message onto ``node_analysis_run``.
    """

    code: str
    message: str


@dataclass
class GraphPlanItem:
    source: CandidateSnapshot
    embedding: list[float] | None
    retrieval: list[RetrievalSnapshot]
    decision: BModelDecision | None
    requested_action: str
    applied_action: str
    target_node_id: uuid.UUID | None = None
    target_node_version: int | None = None
    relation_type: str | None = None
    parent_node_id: uuid.UUID | None = None
    excluded: bool = False
    warnings: list[dict] = field(default_factory=list)
    merge_gate_reason: str | None = None
    #: Set when the B model was invoked and failed. Mutually exclusive with
    #: ``skip_reason``; both stay None on the success path.
    b_model_failure: BModelFailure | None = None
    #: Set when the B model was deliberately not invoked.
    skip_reason: str | None = None
    #: The retrieval stage raised, so its result count is not trustworthy.
    retrieval_failed: bool = False
    #: Sanitized detail for a retrieval-stage failure, persisted on the run.
    retrieval_failure_message: str | None = None


@dataclass(frozen=True)
class GraphMutationPlan:
    generation_run_id: uuid.UUID
    project_id: str
    external_meeting_id: str
    source_request_id: uuid.UUID
    items: tuple[GraphPlanItem, ...]
    warnings: tuple[dict, ...]
    #: Provider model id actually used for this plan's B-model calls, recorded
    #: on ``b_model_result.model``. Never an internal pipeline label. Required,
    #: so a plan cannot be built without knowing which model produced it.
    provider_model: str


@dataclass(frozen=True)
class AutomaticGraphResult:
    generation_run_id: uuid.UUID
    status: str
    created_node_ids: tuple[uuid.UUID, ...]
    merge_operation_ids: tuple[uuid.UUID, ...]
    relation_ids: tuple[uuid.UUID, ...]
    warnings: tuple[dict, ...]
    replayed: bool = False


@dataclass(frozen=True)
class _GenerationClaim:
    run: GenerationRun
    claimed: bool
    replayed: bool


@dataclass(frozen=True)
class _ParentResolution:
    canonical_id: uuid.UUID | None
    gate_reason: str | None


@dataclass(frozen=True)
class _PreparedMergeMember:
    item: GraphPlanItem
    source_node: Node
    requested_target: Node


@dataclass
class _PreparedMergeGroup:
    canonical_target: Node
    members: list[_PreparedMergeMember] = field(default_factory=list)


def _recording_hash(meeting_input: dict) -> str:
    explicit = meeting_input.get("recordingHash")
    if isinstance(explicit, str) and len(explicit) == 64:
        try:
            bytes.fromhex(explicit)
        except ValueError:
            pass
        else:
            return explicit.lower()
    request_id = str(
        meeting_input.get("requestId")
        or f"meeting:{meeting_input['externalMeetingId']}"
    )
    return hashlib.sha256(request_id.encode("utf-8")).hexdigest()


def _claim_generation_run(
    session_factory,
    *,
    project_id: str,
    external_meeting_id: str,
    recording_hash: str,
    pipeline_version: str,
    external_request_id: str | None,
    force_retry: bool,
) -> _GenerationClaim:
    session = session_factory()
    try:
        existing = session.execute(
            select(GenerationRun)
            .where(
                GenerationRun.project_id == project_id,
                GenerationRun.external_meeting_id == external_meeting_id,
                GenerationRun.recording_hash == recording_hash,
                GenerationRun.pipeline_version == pipeline_version,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if existing is None:
            existing = GenerationRun(
                project_id=project_id,
                external_meeting_id=external_meeting_id,
                recording_hash=recording_hash,
                pipeline_version=pipeline_version,
                external_request_id=external_request_id,
                status="EXTRACTING",
                started_at=datetime.now(timezone.utc),
            )
            session.add(existing)
            if session.execute(
                select(MeetingAnalysisCommand.id).where(
                    MeetingAnalysisCommand.project_id == project_id,
                    MeetingAnalysisCommand.meeting_id == external_meeting_id,
                )
            ).scalar_one_or_none() is None:
                stage_analysis_processing(
                    session,
                    project_id=project_id,
                    external_meeting_id=external_meeting_id,
                )
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                return _claim_generation_run(
                    session_factory,
                    project_id=project_id,
                    external_meeting_id=external_meeting_id,
                    recording_hash=recording_hash,
                    pipeline_version=pipeline_version,
                    external_request_id=external_request_id,
                    force_retry=force_retry,
                )
            return _GenerationClaim(existing, True, False)
        if existing.status in _PUBLISHED_STATES:
            session.rollback()
            return _GenerationClaim(existing, False, True)
        if existing.status == "FAILED" or force_retry:
            existing.status = "EXTRACTING"
            existing.failure_code = None
            existing.failure_message = None
            existing.warnings = None
            existing.result_summary = None
            existing.completed_at = None
            existing.started_at = datetime.now(timezone.utc)
            existing.updated_at = datetime.now(timezone.utc)
            if session.execute(
                select(MeetingAnalysisCommand.id).where(
                    MeetingAnalysisCommand.project_id == project_id,
                    MeetingAnalysisCommand.meeting_id == external_meeting_id,
                )
            ).scalar_one_or_none() is None:
                stage_analysis_processing(
                    session,
                    project_id=project_id,
                    external_meeting_id=external_meeting_id,
                )
            session.commit()
            return _GenerationClaim(existing, True, False)
        session.rollback()
        return _GenerationClaim(existing, False, False)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _set_run_stage(
    session_factory,
    *,
    run_id: uuid.UUID,
    project_id: str,
    status: str,
) -> None:
    session = session_factory()
    try:
        run = session.execute(
            select(GenerationRun)
            .where(
                GenerationRun.id == run_id,
                GenerationRun.project_id == project_id,
            )
            .with_for_update()
        ).scalar_one()
        if run.status in _PUBLISHED_STATES:
            raise GenerationRunStateError("published GenerationRun is immutable")
        run.status = status
        run.updated_at = datetime.now(timezone.utc)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _mark_generation_failed(
    session_factory,
    *,
    run_id: uuid.UUID,
    project_id: str,
    code: str,
    error: Exception,
) -> None:
    session = session_factory()
    try:
        run = session.execute(
            select(GenerationRun)
            .where(
                GenerationRun.id == run_id,
                GenerationRun.project_id == project_id,
            )
            .with_for_update()
        ).scalar_one_or_none()
        if run is None:
            session.rollback()
            return
        product_command = session.execute(
            select(MeetingAnalysisCommand.id).where(
                MeetingAnalysisCommand.project_id == project_id,
                MeetingAnalysisCommand.meeting_id == run.external_meeting_id,
            )
        ).scalar_one_or_none()
        if run.status in _PUBLISHED_STATES:
            if product_command is None:
                stage_analysis_failed(
                    session,
                    project_id=project_id,
                    external_meeting_id=run.external_meeting_id,
                    failure_code=code,
                    failure_message=type(error).__name__,
                )
                session.commit()
            else:
                session.rollback()
            return
        if run.status == "FAILED":
            session.rollback()
            return
        run.status = "FAILED"
        run.failure_code = code
        # Only the DB row gets the message. Outbox events and delivery state
        # deliberately carry the exception type alone so a provider payload
        # cannot cross the service boundary.
        run.failure_message = sanitize_text(
            f"{type(error).__name__}: {error}"
        )[:2000]
        run.completed_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)
        if product_command is None:
            session.add(
                OutboxEvent(
                event_type="GRAPH_GENERATION_FAILED",
                aggregate_type="generation_run",
                aggregate_id=str(run.id),
                project_id=project_id,
                schema_version="auto-graph-v1",
                payload={
                    "generationRunId": str(run.id),
                    "projectId": project_id,
                    "externalMeetingId": run.external_meeting_id,
                    "failureCode": code,
                    "errorType": type(error).__name__,
                },
                status="PENDING",
                )
            )
            stage_analysis_failed(
                session,
                project_id=project_id,
                external_meeting_id=run.external_meeting_id,
                failure_code=code,
                failure_message=type(error).__name__,
            )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _source_request_and_candidates(
    session_factory,
    *,
    project_id: str,
    external_meeting_id: str,
    candidate_ids: list[str],
) -> tuple[uuid.UUID, list[CandidateSnapshot], list[dict]]:
    parsed_ids = [uuid.UUID(value) for value in candidate_ids]
    session = session_factory()
    try:
        if not parsed_ids:
            request_id = session.execute(
                select(Request.id)
                .where(
                    Request.project_id == project_id,
                    Request.external_meeting_id == external_meeting_id,
                )
                .order_by(Request.created_at.desc(), Request.id.desc())
            ).scalars().first()
            if request_id is None:
                raise GraphIntegrityError(
                    "automatic graph run has no source Request"
                )
            session.rollback()
            return request_id, [], []
        rows = list(
            session.execute(
                select(NodeCandidate)
                .options(selectinload(NodeCandidate.evidence))
                .where(
                    NodeCandidate.id.in_(parsed_ids),
                    NodeCandidate.project_id == project_id,
                    NodeCandidate.external_meeting_id == external_meeting_id,
                )
                .order_by(NodeCandidate.created_at, NodeCandidate.source_item_id)
            ).scalars().unique()
        )
        if len(rows) != len(set(parsed_ids)):
            raise GraphIntegrityError(
                "candidate set is missing or crosses a project/meeting boundary"
            )
        request_ids = {row.request_id for row in rows}
        if len(request_ids) != 1:
            raise GraphIntegrityError(
                "automatic graph candidates must belong to one Request"
            )
        categories = set(
            session.execute(select(Category.value)).scalars()
        )
        warnings: list[dict] = []
        snapshots: list[CandidateSnapshot] = []
        for row in rows:
            node_type = row.suggested_node_type
            category = row.suggested_category or ""
            title = row.suggested_title.strip()
            if node_type not in _NODE_TYPES or category not in categories or not title:
                warnings.append(
                    {
                        "code": "INVALID_CANDIDATE_SHAPE",
                        "candidateId": str(row.id),
                    }
                )
                continue
            evidence, evidence_warnings = validated_candidate_evidence(
                session,
                candidate=row,
            )
            warnings.extend(evidence_warnings)
            if not evidence:
                warnings.append(
                    {
                        "code": "CANDIDATE_EXCLUDED_NO_VALID_EVIDENCE",
                        "candidateId": str(row.id),
                    }
                )
                continue
            raw_item = row.raw_item or {}
            due_date = (
                str(raw_item.get("dueDate"))
                if raw_item.get("dueDate") not in (None, "")
                else None
            )
            snapshots.append(
                CandidateSnapshot(
                    candidate_id=row.id,
                    source_item_id=row.source_item_id,
                    project_id=row.project_id,
                    external_meeting_id=row.external_meeting_id,
                    node_id=uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"automatic-node:{row.id}",
                    ),
                    node_type=node_type,
                    category=category,
                    title=title,
                    content=row.suggested_content,
                    due_date=due_date,
                    suggested_parent_candidate_id=row.suggested_parent_candidate_id,
                    evidence=tuple(evidence),
                )
            )
        request_id = next(iter(request_ids))
        session.rollback()
        return request_id, snapshots, warnings
    finally:
        session.close()


def _embedding_text(source: CandidateSnapshot) -> str:
    return build_embedding_text_from_parts(
        node_type=source.node_type,
        title=source.title,
        content=source.content,
        evidence_pairs=(
            (row.start_ms, row.source_segment_id or "", row.quoted_text)
            for row in source.evidence
        ),
    )


def _retrieve(
    session_factory,
    *,
    source: CandidateSnapshot,
    embedding: list[float],
    settings: RetrievalSettings,
) -> list[RetrievalSnapshot]:
    session = session_factory()
    try:
        common = dict(
            project_id=source.project_id,
            source_node_id=source.node_id,
            embedding=embedding,
            embedding_model=settings.embedding_model,
            embedding_version=settings.embedding_version,
            embedding_dimension=settings.embedding_dim,
            category=source.category,
            min_similarity=settings.min_similarity,
        )
        merge_rows = search_merge_candidates(
            session,
            node_type=source.node_type,
            top_k=(
                settings.decision_top_k
                if source.node_type == "DECISION"
                else settings.node_top_k
            ),
            **common,
        )
        parent_rows: list[RetrievedNode] = []
        for parent_type in sorted(allowed_parent_types(source.node_type)):
            parent_rows.extend(
                search_link_candidates(
                    session,
                    parent_node_type=parent_type,
                    top_k=settings.node_top_k,
                    **common,
                )
            )
        parent_rows.sort(
            key=lambda row: (-row.similarity, str(row.target_node_id))
        )
        rows = [*merge_rows, *parent_rows[: settings.node_top_k]]
        nodes = {
            row.id: row
            for row in session.execute(
                select(Node).where(
                    Node.project_id == source.project_id,
                    Node.id.in_([item.target_node_id for item in rows]),
                )
            ).scalars()
        }
        result = []
        for rank, item in enumerate(rows, start=1):
            node = nodes.get(item.target_node_id)
            if node is None:
                raise GraphIntegrityError(
                    "Retrieval returned a missing or cross-project Node"
                )
            result.append(
                RetrievalSnapshot(
                    target_node_id=node.id,
                    target_node_version=item.target_node_version,
                    rank=rank,
                    similarity=item.similarity,
                    node_type=node.node_type,
                    category=node.category,
                    title=node.title,
                    content=node.content,
                    graph_state=node.graph_state,
                    parent_id=node.parent_id,
                    due_date=node.due_date,
                )
            )
        session.rollback()
        return result
    finally:
        session.close()


def _source_payload(source: CandidateSnapshot) -> dict[str, Any]:
    return {
        "nodeId": str(source.node_id),
        "nodeVersion": 1,
        "nodeType": source.node_type,
        "category": source.category,
        "title": source.title,
        "content": source.content,
        "dueDate": source.due_date,
        "evidence": [
            {
                "segmentId": row.source_segment_id,
                "quote": row.quoted_text,
                "startMs": row.start_ms,
                "endMs": row.end_ms,
            }
            for row in source.evidence
        ],
    }


def _retrieval_payload(
    retrieval: list[RetrievalSnapshot],
    *,
    same_meeting_parent: GraphPlanItem | None,
) -> list[dict[str, Any]]:
    payload = [
        {
            "nodeId": str(row.target_node_id),
            "nodeVersion": row.target_node_version,
            "nodeType": row.node_type,
            "category": row.category,
            "title": row.title,
            "content": row.content,
            "graphState": row.graph_state,
            "rank": row.rank,
            "similarity": row.similarity,
        }
        for row in retrieval
    ]
    if same_meeting_parent is not None and not same_meeting_parent.excluded:
        payload.append(
            {
                "nodeId": str(same_meeting_parent.source.node_id),
                "nodeVersion": 1,
                "nodeType": same_meeting_parent.source.node_type,
                "category": same_meeting_parent.source.category,
                "title": same_meeting_parent.source.title,
                "content": same_meeting_parent.source.content,
                "graphState": "PLANNED",
                "sameMeetingSuggestedParent": True,
                "parentHintOrigin": "A_MODEL_CANDIDATE_REFERENCE",
            }
        )
    return payload


def _resolve_existing_parent_canonical_id(
    session_factory,
    *,
    project_id: str,
    category: str,
    parent_id: uuid.UUID | None,
    missing_reason: str,
    invalid_reason: str,
) -> _ParentResolution:
    """Resolve an existing structural parent without mutating the graph."""

    if parent_id is None:
        return _ParentResolution(None, missing_reason)
    session = session_factory()
    try:
        try:
            canonical = resolve_canonical_node(
                session,
                project_id=project_id,
                node_id=parent_id,
                expected_node_type="DECISION",
            )
        except (GraphIntegrityError, GraphMutationValidationError):
            session.rollback()
            return _ParentResolution(None, invalid_reason)
        if canonical.graph_state != "ACTIVE" or canonical.category != category:
            session.rollback()
            return _ParentResolution(None, invalid_reason)
        result = _ParentResolution(canonical.id, None)
        session.rollback()
        return result
    finally:
        session.close()


def _resolve_planned_parent_canonical_id(
    session_factory,
    *,
    project_id: str,
    category: str,
    parent_item: GraphPlanItem | None,
) -> _ParentResolution:
    """Resolve a same-meeting Decision through its planned merge outcome."""

    if parent_item is None:
        return _ParentResolution(
            None,
            _MERGE_ACTION_INTENDED_PARENT_MISSING,
        )
    if (
        parent_item.excluded
        or parent_item.source.project_id != project_id
        or parent_item.source.node_type != "DECISION"
        or parent_item.source.category != category
    ):
        return _ParentResolution(
            None,
            _MERGE_ACTION_INTENDED_PARENT_INVALID,
        )
    if parent_item.applied_action == "MERGE":
        return _resolve_existing_parent_canonical_id(
            session_factory,
            project_id=project_id,
            category=category,
            parent_id=parent_item.target_node_id,
            missing_reason=_MERGE_ACTION_INTENDED_PARENT_MISSING,
            invalid_reason=_MERGE_ACTION_INTENDED_PARENT_INVALID,
        )
    if parent_item.applied_action in {"CREATE_NEW", "LINK"}:
        return _ParentResolution(parent_item.source.node_id, None)
    return _ParentResolution(
        None,
        _MERGE_ACTION_INTENDED_PARENT_INVALID,
    )


def _action_parent_gate(
    *,
    intended_parent: _ParentResolution,
    target_parent: _ParentResolution,
) -> str | None:
    if intended_parent.gate_reason is not None:
        return intended_parent.gate_reason
    if target_parent.gate_reason is not None:
        return target_parent.gate_reason
    if intended_parent.canonical_id != target_parent.canonical_id:
        return _MERGE_ACTION_PARENT_CONFLICT
    return None


def _merge_item_order_key(
    item: GraphPlanItem,
) -> tuple[int, str, str, str]:
    """Use transcript order before stable plan and UUID tie-breakers."""

    evidence_order = min(
        (
            (
                spec.start_ms if spec.start_ms is not None else 2**63 - 1,
                spec.source_segment_id or "",
            )
            for spec in item.source.evidence
        ),
        default=(2**63 - 1, ""),
    )
    return (
        evidence_order[0],
        evidence_order[1],
        item.source.source_item_id,
        str(item.source.node_id),
    )


def _target_retrieval_snapshot(
    item: GraphPlanItem,
) -> RetrievalSnapshot | None:
    if item.target_node_id is None:
        return None
    return next(
        (
            row
            for row in item.retrieval
            if row.target_node_id == item.target_node_id
        ),
        None,
    )


def _downgrade_merge_item(
    *,
    item: GraphPlanItem,
    reason: str,
    warnings: list[dict],
    record_on_item: bool,
) -> None:
    item.applied_action = "CREATE_NEW"
    item.merge_gate_reason = reason
    item.target_node_id = None
    item.target_node_version = None
    item.parent_node_id = None
    warning = {
        "code": reason,
        "candidateId": str(item.source.candidate_id),
        "requestedAction": "MERGE",
        "appliedAction": "CREATE_NEW",
    }
    if record_on_item:
        item.warnings.append(warning)
    warnings.append(warning)


def _identity_gate(
    *,
    source: CandidateSnapshot,
    target: RetrievalSnapshot,
    decision: BModelDecision,
    policy: AutoMergePolicy,
    intended_parent: _ParentResolution,
    target_parent: _ParentResolution,
) -> str | None:
    if policy.min_similarity is None or policy.min_margin is None:
        return "MERGE_POLICY_UNCALIBRATED"
    if target.rank != 1:
        return "MERGE_TARGET_NOT_RETRIEVAL_TOP1"
    if target.similarity < policy.min_similarity:
        return "MERGE_BELOW_ABSOLUTE_THRESHOLD"
    identity = decision.metadata.get("identityBasis")
    conflicts = decision.metadata.get("conflictsChecked")
    if not isinstance(identity, dict):
        return "MERGE_IDENTITY_BASIS_MISSING"
    required = {
        "same_subject",
        "same_outcome_or_task",
        "same_scope",
        "same_time_or_scope",
    }
    if source.node_type == "ACTION":
        required.add("same_owner_if_required")
    if any(identity.get(key) is not True for key in required):
        return "MERGE_IDENTITY_NOT_PROVEN"
    if not isinstance(conflicts, (dict, list)) or not conflicts:
        return "MERGE_CONFLICT_CHECK_MISSING"
    conflict_rows = (
        list(conflicts.values())
        if isinstance(conflicts, dict)
        else conflicts
    )
    for value in conflict_rows:
        result = value.get("result") if isinstance(value, dict) else value
        if str(result).upper() not in {
            "NO_CONFLICT",
            "MATCH",
            "PASS",
            "SAME",
            "NONE",
        }:
            return "MERGE_STRUCTURED_CONFLICT"
    if source.node_type == "ACTION":
        if (
            source.due_date
            and target.due_date
            and source.due_date != target.due_date
        ):
            return "MERGE_ACTION_DUE_DATE_CONFLICT"
        parent_gate_reason = _action_parent_gate(
            intended_parent=intended_parent,
            target_parent=target_parent,
        )
        if parent_gate_reason is not None:
            return parent_gate_reason
    return None


def _validate_link_target(
    *,
    source: CandidateSnapshot,
    decision: BModelDecision,
    retrieval: list[RetrievalSnapshot],
    same_meeting_parent: GraphPlanItem | None,
) -> tuple[uuid.UUID, int] | None:
    target_id = decision.targetNodeId
    if target_id is None:
        return None
    for row in retrieval:
        if row.target_node_id != target_id:
            continue
        if decision.relationType and decision.relationType.value == "ATTACHED_TO":
            allowed = (
                {"DECISION"}
                if source.node_type == "ACTION"
                else {"DECISION", "ACTION"}
                if source.node_type == "ISSUE"
                else set()
            )
            if (
                row.graph_state != "ACTIVE"
                or row.node_type not in allowed
                or row.category != source.category
            ):
                return None
        return row.target_node_id, row.target_node_version
    if (
        same_meeting_parent is not None
        and same_meeting_parent.source.node_id == target_id
        and decision.relationType
        and decision.relationType.value == "ATTACHED_TO"
    ):
        allowed = (
            {"DECISION"}
            if source.node_type == "ACTION"
            else {"DECISION", "ACTION"}
            if source.node_type == "ISSUE"
            else set()
        )
        if (
            same_meeting_parent.source.node_type in allowed
            and same_meeting_parent.source.category == source.category
        ):
            return target_id, 1
    return None


def build_graph_mutation_plan(
    session_factory,
    *,
    generation_run_id: uuid.UUID,
    project_id: str,
    external_meeting_id: str,
    source_request_id: uuid.UUID,
    candidates: list[CandidateSnapshot],
    embedding_client: EmbeddingClient,
    b_model_client: BModelClient,
    retrieval_settings: RetrievalSettings,
    merge_policy: AutoMergePolicy,
    pipeline_label: str,
) -> GraphMutationPlan:
    """Call external adapters and build a side-effect-free Decision-first Plan."""

    # Resolved once, up front: b_model_result.model is NOT NULL, and a blank
    # provider model would silently record which model produced a decision as
    # "". A client without one violates the BModelClient port.
    provider_model = str(getattr(b_model_client, "provider_model", "") or "").strip()
    if not provider_model:
        raise ValueError(
            "b_model_client.provider_model must be a non-empty provider model id "
            "(B_MODEL_NAME -> OPENAI_MODEL); internal execution labels belong in "
            "pipeline_label"
        )

    warnings: list[dict] = []
    items: list[GraphPlanItem] = []
    planned_by_candidate: dict[uuid.UUID, GraphPlanItem] = {}
    ordered = sorted(
        candidates,
        key=lambda row: (
            0 if row.node_type == "DECISION" else 1,
            row.source_item_id,
            str(row.candidate_id),
        ),
    )
    current_phase = None
    for source in ordered:
        phase = (
            "DECISION_ANALYZING"
            if source.node_type == "DECISION"
            else "DEPENDENT_ANALYZING"
        )
        if phase != current_phase:
            _set_run_stage(
                session_factory,
                run_id=generation_run_id,
                project_id=project_id,
                status=phase,
            )
            current_phase = phase
        item = GraphPlanItem(
            source=source,
            embedding=None,
            retrieval=[],
            decision=None,
            requested_action="CREATE_NEW",
            applied_action="CREATE_NEW",
        )
        parent_item = (
            planned_by_candidate.get(source.suggested_parent_candidate_id)
            if source.suggested_parent_candidate_id is not None
            else None
        )
        try:
            raw_embedding = embedding_client.embed(
                text=_embedding_text(source),
                model=retrieval_settings.embedding_model,
                dimensions=retrieval_settings.embedding_dim,
            )
            item.embedding = validate_embedding(
                raw_embedding,
                expected_dimension=retrieval_settings.embedding_dim,
            )
            item.retrieval = _retrieve(
                session_factory,
                source=source,
                embedding=item.embedding,
                settings=retrieval_settings,
            )
        except Exception as exc:
            # Retrieval never completed, so the B model is not attempted at
            # all: that is a skip, and the retrieval stage itself is FAILED.
            # An embedding-provider outage has to be as visible here as a
            # B-model outage is below - the class name alone cannot tell a 401
            # from a 429 from a dropped connection.
            _, detail = describe_b_model_failure(exc)
            item.retrieval_failed = True
            item.skip_reason = "RETRIEVAL_FAILED"
            item.retrieval_failure_message = detail
            warning = {
                "code": "EMBEDDING_OR_RETRIEVAL_FAILED_CREATE_NEW",
                "candidateId": str(source.candidate_id),
                "errorType": type(exc).__name__,
                "failureMessage": detail,
            }
            logger.error(
                "retrieval stage failed project_id=%s meeting=%s run_id=%s "
                "candidate_id=%s detail=%s",
                project_id,
                external_meeting_id,
                generation_run_id,
                source.candidate_id,
                detail,
            )
            item.warnings.append(warning)
            warnings.append(warning)
            items.append(item)
            planned_by_candidate[source.candidate_id] = item
            continue

        candidate_payload = _retrieval_payload(
            item.retrieval,
            same_meeting_parent=parent_item,
        )
        if not candidate_payload:
            item.skip_reason = "NO_RETRIEVAL_CANDIDATES"
            item.warnings.append(
                {
                    "code": "NO_RETRIEVAL_CANDIDATES_CREATE_NEW",
                    "candidateId": str(source.candidate_id),
                }
            )
            warnings.extend(item.warnings)
            items.append(item)
            planned_by_candidate[source.candidate_id] = item
            continue
        # Built outside the try: a local bug here (renamed field, bad type) is
        # not a provider failure and must not be persisted as one.
        source_payload = _source_payload(source)
        try:
            raw = b_model_client.recommend(
                source_node=source_payload,
                retrieval_candidates=candidate_payload,
            )
            decision = BModelDecision.model_validate(raw)
            item.decision = decision
            item.requested_action = decision.recommendation.value
        except Exception as exc:
            # The provider was called and did not deliver: record it as a
            # failure with a stable code, never as "no recommendation". The
            # item still falls back to CREATE_NEW so the meeting can publish,
            # but the run row makes the failure visible to operators.
            failure_code, failure_message = describe_b_model_failure(exc)
            item.b_model_failure = BModelFailure(failure_code, failure_message)
            warning = {
                "code": "B_MODEL_FAILED_CREATE_NEW",
                "candidateId": str(source.candidate_id),
                "errorType": type(exc).__name__,
                "failureCode": failure_code,
                "failureMessage": failure_message,
            }
            logger.error(
                "B-model call failed project_id=%s meeting=%s run_id=%s "
                "candidate_id=%s model=%s failure_code=%s detail=%s",
                project_id,
                external_meeting_id,
                generation_run_id,
                source.candidate_id,
                provider_model,
                failure_code,
                failure_message,
            )
            item.warnings.append(warning)
            warnings.append(warning)
            items.append(item)
            planned_by_candidate[source.candidate_id] = item
            continue

        decision = item.decision
        assert decision is not None
        if decision.recommendation is RecommendationType.LINK:
            target = _validate_link_target(
                source=source,
                decision=decision,
                retrieval=item.retrieval,
                same_meeting_parent=parent_item,
            )
            if target is None:
                item.applied_action = "CREATE_NEW"
                item.warnings.append(
                    {
                        "code": "INVALID_LINK_RECOMMENDATION_CREATE_NEW",
                        "candidateId": str(source.candidate_id),
                    }
                )
            else:
                item.applied_action = "LINK"
                item.target_node_id, item.target_node_version = target
                item.relation_type = decision.relationType.value
                if item.relation_type == "ATTACHED_TO":
                    item.parent_node_id = item.target_node_id
        elif decision.recommendation is RecommendationType.MERGE:
            target = next(
                (
                    row
                    for row in item.retrieval
                    if row.target_node_id == decision.targetNodeId
                ),
                None,
            )
            if (
                merge_policy.min_similarity is None
                or merge_policy.min_margin is None
            ):
                item.merge_gate_reason = "MERGE_POLICY_UNCALIBRATED"
            elif target is None or target.node_type != source.node_type:
                item.merge_gate_reason = "MERGE_TARGET_NOT_VALID_RETRIEVAL"
            elif target.category != source.category:
                # Defense in depth: Retrieval already hard-filters category, so
                # reaching here means the candidate set and the target snapshot
                # disagree. Never fold two different categories into one Node -
                # downgrade to CREATE_NEW instead.
                item.merge_gate_reason = "MERGE_CATEGORY_MISMATCH"
            elif target.graph_state != "ACTIVE":
                # Only an ACTIVE canonical Node may absorb another.
                item.merge_gate_reason = "MERGE_TARGET_NOT_ACTIVE"
            else:
                other_merge_scores = [
                    row.similarity
                    for row in item.retrieval
                    if row.node_type == source.node_type
                    and row.target_node_id != target.target_node_id
                ]
                second_score = (
                    max(other_merge_scores) if other_merge_scores else None
                )
                if (
                    second_score is not None
                    and target.similarity - second_score < (
                        merge_policy.min_margin
                        if merge_policy.min_margin is not None
                        else float("inf")
                    )
                ):
                    item.merge_gate_reason = "MERGE_MARGIN_TOO_SMALL"
                else:
                    intended_parent = _ParentResolution(None, None)
                    target_parent = _ParentResolution(None, None)
                    if source.node_type == "ACTION":
                        intended_parent = (
                            _resolve_planned_parent_canonical_id(
                                session_factory,
                                project_id=project_id,
                                category=source.category,
                                parent_item=parent_item,
                            )
                        )
                        target_parent = (
                            _resolve_existing_parent_canonical_id(
                                session_factory,
                                project_id=project_id,
                                category=source.category,
                                parent_id=target.parent_id,
                                missing_reason=(
                                    _MERGE_ACTION_TARGET_PARENT_MISSING
                                ),
                                invalid_reason=(
                                    _MERGE_ACTION_TARGET_PARENT_INVALID
                                ),
                            )
                        )
                        item.parent_node_id = (
                            intended_parent.canonical_id
                        )
                    item.merge_gate_reason = _identity_gate(
                        source=source,
                        target=target,
                        decision=decision,
                        policy=merge_policy,
                        intended_parent=intended_parent,
                        target_parent=target_parent,
                    )
            if item.merge_gate_reason is None:
                item.applied_action = "MERGE"
                item.target_node_id = target.target_node_id
                item.target_node_version = target.target_node_version
            else:
                item.applied_action = "CREATE_NEW"
                item.warnings.append(
                    {
                        "code": item.merge_gate_reason,
                        "candidateId": str(source.candidate_id),
                        "requestedAction": "MERGE",
                        "appliedAction": "CREATE_NEW",
                    }
                )
        else:
            item.applied_action = "CREATE_NEW"
        warnings.extend(item.warnings)
        items.append(item)
        planned_by_candidate[source.candidate_id] = item

    return GraphMutationPlan(
        generation_run_id=generation_run_id,
        project_id=project_id,
        external_meeting_id=external_meeting_id,
        source_request_id=source_request_id,
        items=tuple(items),
        warnings=tuple(warnings),
        provider_model=provider_model,
    )


def _analysis_input_hash(item: GraphPlanItem, settings: RetrievalSettings) -> str:
    return hashlib.sha256(
        json.dumps(
            [
                "automatic-analysis-v1",
                _embedding_text(item.source),
                settings.config_version,
                settings.embedding_model,
                settings.embedding_version,
            ],
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _relation_pair(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    relation_type: str,
) -> tuple[uuid.UUID, uuid.UUID]:
    if relation_type == "RELATED_TO":
        pair = sorted((source_id, target_id), key=str)
        return pair[0], pair[1]
    return source_id, target_id


def _create_or_reactivate_relation(
    session,
    *,
    project_id: str,
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    relation_type: str,
    generation_run_id: uuid.UUID,
) -> Relation:
    from_id, to_id = _relation_pair(source_id, target_id, relation_type)
    existing = session.execute(
        select(Relation).where(
            Relation.project_id == project_id,
            Relation.from_node_id == from_id,
            Relation.to_node_id == to_id,
            Relation.relation_type == relation_type,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.status = "CONFIRMED"
        existing.actor_type = "SYSTEM"
        existing.valid_to = None
        return existing
    relation = Relation(
        project_id=project_id,
        from_node_id=from_id,
        to_node_id=to_id,
        relation_type=relation_type,
        status="CONFIRMED",
        actor_type="SYSTEM",
        generation_run_id=generation_run_id,
        valid_from=datetime.now(timezone.utc),
    )
    session.add(relation)
    session.flush()
    return relation


def _b_model_trace_state(item: GraphPlanItem) -> dict[str, str | None]:
    """Map one planned item onto its ``node_analysis_run`` B-model columns.

    Three outcomes, never collapsed into each other:
      SUCCEEDED - a validated decision exists.
      FAILED    - the provider was called and did not deliver one.
      SKIPPED   - the provider was deliberately not called.
    """

    if item.decision is not None:
        return {
            "b_model_status": "SUCCEEDED",
            "b_model_skip_reason": None,
            "b_model_failure_code": None,
            "b_model_failure_message": None,
        }
    if item.b_model_failure is not None:
        return {
            "b_model_status": "FAILED",
            "b_model_skip_reason": None,
            "b_model_failure_code": item.b_model_failure.code,
            "b_model_failure_message": item.b_model_failure.message,
        }
    if item.skip_reason is None:
        # Never guess a plausible reason: that is exactly how every outcome
        # collapsed into NO_VALID_B_MODEL_RESULT. A new early-continue in the
        # planning loop that forgets to set skip_reason must be loud.
        logger.error(
            "plan item candidate_id=%s has no decision, no failure and no "
            "skip_reason; the B-model outcome is unknown",
            item.source.candidate_id,
        )
    return {
        "b_model_status": "SKIPPED",
        # Older rows used NO_VALID_B_MODEL_RESULT for every outcome; a skip now
        # names the condition that stopped the call from happening.
        "b_model_skip_reason": item.skip_reason or "UNKNOWN_SKIP_REASON",
        "b_model_failure_code": None,
        "b_model_failure_message": None,
    }


def _run_failure_columns(item: GraphPlanItem) -> dict[str, str | None]:
    """Mirror a stage failure onto the run-level failure columns.

    ``node_analysis_run.status`` stays COMPLETED because the automatic pipeline
    did publish the Node, but an operator querying ``failure_code IS NOT NULL``
    must not get zero rows during a total provider outage.
    """

    if item.b_model_failure is not None:
        return {
            "failure_code": item.b_model_failure.code,
            "failure_message": item.b_model_failure.message,
        }
    if item.retrieval_failed:
        return {
            "failure_code": "RETRIEVAL_FAILED",
            "failure_message": item.retrieval_failure_message,
        }
    return {"failure_code": None, "failure_message": None}


def _persist_analysis_trace(
    session,
    *,
    node: Node,
    item: GraphPlanItem,
    settings: RetrievalSettings,
    provider_model: str,
    pipeline_label: str,
) -> NodeAnalysisRun:
    now = datetime.now(timezone.utc)
    input_hash = _analysis_input_hash(item, settings)
    run = NodeAnalysisRun(
        source_node_id=node.id,
        source_node_version=1,
        analysis_input_hash=input_hash,
        analysis_input_hash_version="automatic-analysis-v1",
        retrieval_config_version=settings.config_version,
        embedding_model=settings.embedding_model,
        embedding_version=settings.embedding_version,
        retrieval_status=("FAILED" if item.retrieval_failed else "COMPLETED"),
        retrieval_result_count=len(item.retrieval),
        # A stage that failed has no completion time.
        retrieval_completed_at=(None if item.retrieval_failed else now),
        **_b_model_trace_state(item),
        b_model_completed_at=now,
        attempt=1,
        # The Node is still published, so the run itself completed; the
        # run-level failure columns are what makes a stage failure findable
        # by the usual `WHERE failure_code IS NOT NULL` query.
        status="COMPLETED",
        **_run_failure_columns(item),
        requested_by="AUTOMATIC_PIPELINE",
        started_at=now,
        completed_at=now,
    )
    session.add(run)
    session.flush()
    for result in item.retrieval:
        session.add(
            RetrievalResult(
                analysis_run_id=run.id,
                target_node_id=result.target_node_id,
                target_node_version=result.target_node_version,
                rank=result.rank,
                similarity=result.similarity,
            )
        )
    if item.decision is not None:
        decision = item.decision
        target_id = (
            item.target_node_id
            if decision.recommendation is not RecommendationType.CREATE_NEW
            else None
        )
        target_version = (
            item.target_node_version if target_id is not None else None
        )
        # A recommendation to a non-retrieval planned parent is valid for LINK,
        # but BModelResult's target FK is available because all planned Nodes
        # have already been inserted in this transaction.
        session.add(
            BModelResult(
                project_id=node.project_id,
                analysis_run_id=run.id,
                source_node_id=node.id,
                source_node_version=1,
                recommendation=(
                    decision.recommendation.value
                    if target_id is not None
                    else "CREATE_NEW"
                ),
                target_node_id=target_id,
                target_node_version=target_version,
                relation_type=(
                    decision.relationType.value
                    if target_id is not None
                    and decision.recommendation is RecommendationType.LINK
                    else None
                ),
                suggested_title=decision.suggestedTitle.strip(),
                suggested_content=decision.suggestedContent,
                reason=decision.reason.strip(),
                # model = the provider model actually called (e.g. gpt-5.2).
                # model_version = the internal analysis contract version. The
                # pipeline label is metadata, never either of these.
                model=provider_model,
                model_version="automatic-v1",
                metadata_json={
                    **decision.metadata,
                    "requestedRecommendation": decision.recommendation.value,
                    "requestedTargetNodeId": (
                        str(decision.targetNodeId)
                        if decision.targetNodeId is not None
                        else None
                    ),
                    "appliedRecommendation": item.applied_action,
                    "mergeGateReason": item.merge_gate_reason,
                    "pipelineLabel": pipeline_label,
                },
                validation_status="VALIDATED",
            )
        )
    node.current_analysis_run_id = run.id
    node.analysis_input_hash = input_hash
    node.analysis_status = "ANALYZED"
    return run


def _downgrade_merge_at_apply(
    *,
    item: GraphPlanItem,
    reason: str,
    apply_warnings: list[dict],
) -> None:
    _downgrade_merge_item(
        item=item,
        reason=reason,
        warnings=apply_warnings,
        record_on_item=False,
    )


def _resolve_action_parent_for_apply(
    session,
    *,
    project_id: str,
    category: str,
    parent_id: uuid.UUID | None,
    missing_reason: str,
    invalid_reason: str,
) -> _ParentResolution:
    if parent_id is None:
        return _ParentResolution(None, missing_reason)
    try:
        canonical = resolve_canonical_node(
            session,
            project_id=project_id,
            node_id=parent_id,
            expected_node_type="DECISION",
            for_update=True,
        )
    except (GraphIntegrityError, GraphMutationValidationError):
        return _ParentResolution(None, invalid_reason)
    if canonical.graph_state != "ACTIVE" or canonical.category != category:
        return _ParentResolution(None, invalid_reason)
    return _ParentResolution(canonical.id, None)


def _deduplicate_evidence_specs(
    *,
    project_id: str,
    specs: list[EvidenceSpec],
) -> list[EvidenceSpec]:
    deduplicated: dict[str, EvidenceSpec] = {}
    for spec in specs:
        deduplicated.setdefault(evidence_hash(project_id, spec), spec)
    return list(deduplicated.values())


def _apply_planned_logical_merge(
    session,
    *,
    plan: GraphMutationPlan,
    item: GraphPlanItem,
    source_node: Node,
    target_node: Node,
) -> uuid.UUID:
    decision = item.decision
    assert decision is not None
    if source_node.graph_state != "UNATTACHED" or source_node.parent_id is not None:
        raise GraphIntegrityError("automatic merge source must be an UNATTACHED leaf")
    if session.execute(
        select(Node.id).where(
            Node.project_id == plan.project_id,
            Node.parent_id == source_node.id,
            Node.deleted_at.is_(None),
        )
    ).first() is not None:
        raise GraphIntegrityError("automatic merge source must not have children")
    canonical_target = resolve_canonical_node(
        session,
        project_id=plan.project_id,
        node_id=target_node.id,
        expected_node_type=source_node.node_type,
        for_update=True,
    )
    if (
        canonical_target.graph_state != "ACTIVE"
        or canonical_target.category != source_node.category
    ):
        raise GraphMutationValidationError(
            "automatic merge target must be ACTIVE with the same category"
        )
    suggested_title = decision.suggestedTitle.strip()
    if not suggested_title:
        raise GraphMutationValidationError("automatic merge title must not be blank")
    user_content_protected = canonical_target.last_actor_type == "USER"
    evidence_specs = _deduplicate_evidence_specs(
        project_id=plan.project_id,
        specs=[
            *current_revision_evidence_specs(session, node=canonical_target),
            *current_revision_evidence_specs(session, node=source_node),
        ],
    )
    create_node_revision(
        session,
        node=canonical_target,
        title=(canonical_target.title if user_content_protected else suggested_title),
        content=(
            canonical_target.content
            if user_content_protected
            else decision.suggestedContent
        ),
        node_type=canonical_target.node_type,
        category=canonical_target.category,
        due_date=canonical_target.due_date,
        created_by_type="SYSTEM",
        created_by_id="AUTOMATIC_PIPELINE",
        generation_run_id=plan.generation_run_id,
        evidence_specs=evidence_specs,
        requires_evidence=True,
    )
    if user_content_protected:
        # The revision itself is SYSTEM-authored because the automatic merge
        # appended Evidence, but the last user-authored title/content remain the
        # protected projection for later automatic merges.
        canonical_target.last_actor_type = "USER"
    mark_node_embedding_stale(session, node=canonical_target)
    source_node.parent_id = None
    retrieval = next(
        row
        for row in item.retrieval
        if row.target_node_id == target_node.id
    )
    operation = apply_logical_merge(
        session,
        project_id=plan.project_id,
        source=source_node,
        target=canonical_target,
        actor_type="SYSTEM",
        actor_id="AUTOMATIC_PIPELINE",
        generation_run_id=plan.generation_run_id,
        reason_code="AUTO_IDENTITY_MATCH",
        reason_text=decision.reason,
        identity_basis=decision.metadata.get("identityBasis"),
        conflicts_checked=decision.metadata.get("conflictsChecked"),
        model_confidence=(
            float(decision.metadata["confidence"])
            if isinstance(decision.metadata.get("confidence"), (int, float))
            else None
        ),
        retrieval_rank=retrieval.rank,
        retrieval_score=retrieval.similarity,
        second_retrieval_score=(
            item.retrieval[1].similarity
            if len(item.retrieval) > 1
            else None
        ),
    )
    return operation.id


def _target_version_valid_for_apply(
    session,
    *,
    plan: GraphMutationPlan,
    target: Node,
    expected_version: int | None,
) -> bool:
    if expected_version is None or target.version == expected_version:
        return True
    if target.version < expected_version or target.current_revision_id is None:
        return False
    revision = session.get(NodeRevision, target.current_revision_id)
    return bool(
        revision is not None
        and revision.generation_run_id == plan.generation_run_id
        and revision.created_by_type == "SYSTEM"
        and revision.created_by_id == "AUTOMATIC_PIPELINE"
    )


def _apply_planned_merge(
    session,
    *,
    plan: GraphMutationPlan,
    item: GraphPlanItem,
    nodes_by_planned_id: dict[uuid.UUID, Node],
    locked_targets: dict[uuid.UUID, Node],
    apply_warnings: list[dict],
) -> uuid.UUID | None:
    if item.applied_action != "MERGE" or item.target_node_id is None:
        return None
    source_node = nodes_by_planned_id[item.source.node_id]
    target_node = (
        nodes_by_planned_id.get(item.target_node_id)
        or locked_targets.get(item.target_node_id)
    )
    if target_node is None:
        _downgrade_merge_at_apply(
            item=item,
            reason="MERGE_TARGET_MISSING_CREATE_NEW",
            apply_warnings=apply_warnings,
        )
        return None
    if not _target_version_valid_for_apply(
        session,
        plan=plan,
        target=target_node,
        expected_version=item.target_node_version,
    ):
        _downgrade_merge_at_apply(
            item=item,
            reason="MERGE_TARGET_VERSION_CHANGED_CREATE_NEW",
            apply_warnings=apply_warnings,
        )
        return None
    canonical_target = resolve_canonical_node(
        session,
        project_id=plan.project_id,
        node_id=target_node.id,
        expected_node_type=source_node.node_type,
        for_update=True,
    )
    if (
        canonical_target.graph_state != "ACTIVE"
        or canonical_target.category != source_node.category
    ):
        _downgrade_merge_at_apply(
            item=item,
            reason="MERGE_TARGET_NOT_ACTIVE_SAME_CATEGORY_CREATE_NEW",
            apply_warnings=apply_warnings,
        )
        return None
    if source_node.node_type == "ACTION":
        intended_parent = _resolve_action_parent_for_apply(
            session,
            project_id=plan.project_id,
            category=source_node.category,
            parent_id=item.parent_node_id,
            missing_reason=_MERGE_ACTION_INTENDED_PARENT_MISSING,
            invalid_reason=_MERGE_ACTION_INTENDED_PARENT_INVALID,
        )
        target_parent = _resolve_action_parent_for_apply(
            session,
            project_id=plan.project_id,
            category=canonical_target.category,
            parent_id=canonical_target.parent_id,
            missing_reason=_MERGE_ACTION_TARGET_PARENT_MISSING,
            invalid_reason=_MERGE_ACTION_TARGET_PARENT_INVALID,
        )
        parent_gate_reason = _action_parent_gate(
            intended_parent=intended_parent,
            target_parent=target_parent,
        )
        if parent_gate_reason is not None:
            _downgrade_merge_at_apply(
                item=item,
                reason=parent_gate_reason,
                apply_warnings=apply_warnings,
            )
            return None
    return _apply_planned_logical_merge(
        session,
        plan=plan,
        item=item,
        source_node=source_node,
        target_node=target_node,
    )


def _target_version_matches_plan(
    session,
    *,
    plan: GraphMutationPlan,
    item: GraphPlanItem,
    requested_target: Node,
    canonical_target: Node,
) -> bool:
    return _target_version_valid_for_apply(
        session,
        plan=plan,
        target=canonical_target,
        expected_version=item.target_node_version,
    )


def _prepare_dependent_merge_groups(
    session,
    *,
    plan: GraphMutationPlan,
    nodes_by_planned_id: dict[uuid.UUID, Node],
    locked_targets: dict[uuid.UUID, Node],
    apply_warnings: list[dict],
) -> list[_PreparedMergeGroup]:
    """Validate external versions before any same-group target mutation."""

    groups: dict[uuid.UUID, _PreparedMergeGroup] = {}
    merge_items = sorted(
        (
            item
            for item in plan.items
            if item.source.node_type != "DECISION"
            and item.applied_action == "MERGE"
            and item.target_node_id is not None
        ),
        key=_merge_item_order_key,
    )
    for item in merge_items:
        source_node = nodes_by_planned_id[item.source.node_id]
        target_node = (
            nodes_by_planned_id.get(item.target_node_id)
            or locked_targets.get(item.target_node_id)
        )
        if target_node is None:
            _downgrade_merge_at_apply(
                item=item,
                reason="MERGE_TARGET_MISSING_CREATE_NEW",
                apply_warnings=apply_warnings,
            )
            continue
        try:
            canonical_target = resolve_canonical_node(
                session,
                project_id=plan.project_id,
                node_id=target_node.id,
                expected_node_type=source_node.node_type,
                for_update=True,
            )
        except (GraphIntegrityError, GraphMutationValidationError):
            _downgrade_merge_at_apply(
                item=item,
                reason="MERGE_TARGET_NOT_VALID_RETRIEVAL",
                apply_warnings=apply_warnings,
            )
            continue

        # A partially recovered source already redirected to this target is a
        # no-op. It must not create another MergeOperation.
        if source_node.graph_state == "MERGED":
            source_target = resolve_canonical_node(
                session,
                project_id=plan.project_id,
                node_id=source_node.id,
                expected_node_type=source_node.node_type,
                for_update=True,
            )
            if source_target.id == canonical_target.id:
                continue
            raise GraphIntegrityError(
                "partially merged source points to another canonical target"
            )

        if not _target_version_matches_plan(
            session,
            plan=plan,
            item=item,
            requested_target=target_node,
            canonical_target=canonical_target,
        ):
            _downgrade_merge_at_apply(
                item=item,
                reason="MERGE_TARGET_VERSION_CHANGED_CREATE_NEW",
                apply_warnings=apply_warnings,
            )
            continue
        if source_node.id == canonical_target.id:
            _downgrade_merge_at_apply(
                item=item,
                reason="MERGE_TARGET_NOT_VALID_RETRIEVAL",
                apply_warnings=apply_warnings,
            )
            continue
        group = groups.setdefault(
            canonical_target.id,
            _PreparedMergeGroup(canonical_target=canonical_target),
        )
        group.members.append(
            _PreparedMergeMember(
                item=item,
                source_node=source_node,
                requested_target=target_node,
            )
        )
    return [
        groups[target_id]
        for target_id in sorted(groups, key=str)
    ]


def _apply_dependent_merge_groups(
    session,
    *,
    plan: GraphMutationPlan,
    nodes_by_planned_id: dict[uuid.UUID, Node],
    locked_targets: dict[uuid.UUID, Node],
    apply_warnings: list[dict],
) -> list[uuid.UUID]:
    groups = _prepare_dependent_merge_groups(
        session,
        plan=plan,
        nodes_by_planned_id=nodes_by_planned_id,
        locked_targets=locked_targets,
        apply_warnings=apply_warnings,
    )
    operation_ids: list[uuid.UUID] = []
    for group in groups:
        canonical_target = group.canonical_target
        accepted: list[_PreparedMergeMember] = []
        target_parent = _ParentResolution(None, None)
        if canonical_target.node_type == "ACTION":
            target_parent = _resolve_action_parent_for_apply(
                session,
                project_id=plan.project_id,
                category=canonical_target.category,
                parent_id=canonical_target.parent_id,
                missing_reason=_MERGE_ACTION_TARGET_PARENT_MISSING,
                invalid_reason=_MERGE_ACTION_TARGET_PARENT_INVALID,
            )

        for member in sorted(
            group.members,
            key=lambda row: _merge_item_order_key(row.item),
        ):
            item = member.item
            source_node = member.source_node
            if canonical_target.node_type == "ACTION":
                intended_parent = _resolve_action_parent_for_apply(
                    session,
                    project_id=plan.project_id,
                    category=source_node.category,
                    parent_id=item.parent_node_id,
                    missing_reason=_MERGE_ACTION_INTENDED_PARENT_MISSING,
                    invalid_reason=_MERGE_ACTION_INTENDED_PARENT_INVALID,
                )
                parent_gate_reason = _action_parent_gate(
                    intended_parent=intended_parent,
                    target_parent=target_parent,
                )
                if parent_gate_reason is not None:
                    _downgrade_merge_at_apply(
                        item=item,
                        reason=parent_gate_reason,
                        apply_warnings=apply_warnings,
                    )
                    continue
            accepted.append(member)

        for member in accepted:
            operation_ids.append(
                _apply_planned_logical_merge(
                    session,
                    plan=plan,
                    item=member.item,
                    source_node=member.source_node,
                    target_node=member.requested_target,
                )
            )
    return operation_ids


def apply_graph_mutation_plan(
    session_factory,
    *,
    plan: GraphMutationPlan,
    retrieval_settings: RetrievalSettings,
    pipeline_label: str,
) -> AutomaticGraphResult:
    """Atomically publish one complete plan or nothing."""

    session = session_factory()
    try:
        run = session.execute(
            select(GenerationRun)
            .where(
                GenerationRun.id == plan.generation_run_id,
                GenerationRun.project_id == plan.project_id,
            )
            .with_for_update()
        ).scalar_one()
        if run.status in _PUBLISHED_STATES:
            summary = run.result_summary or {}
            session.rollback()
            return AutomaticGraphResult(
                generation_run_id=run.id,
                status=run.status,
                created_node_ids=tuple(
                    uuid.UUID(value)
                    for value in summary.get("createdNodeIds", [])
                ),
                merge_operation_ids=tuple(
                    uuid.UUID(value)
                    for value in summary.get("mergeOperationIds", [])
                ),
                relation_ids=tuple(
                    uuid.UUID(value)
                    for value in summary.get("relationIds", [])
                ),
                warnings=tuple(run.warnings or []),
                replayed=True,
            )
        if run.status != "VALIDATING":
            raise GenerationRunStateError(
                f"GenerationRun is not applicable: {run.status}"
            )
        run.status = "APPLYING"
        run.updated_at = datetime.now(timezone.utc)

        existing_target_ids = sorted(
            {
                item.target_node_id
                for item in plan.items
                if item.target_node_id is not None
                and all(
                    item.target_node_id != other.source.node_id
                    for other in plan.items
                )
            },
            key=str,
        )
        locked_targets = {
            node.id: node
            for node in session.execute(
                select(Node)
                .where(
                    Node.project_id == plan.project_id,
                    Node.id.in_(existing_target_ids),
                    Node.deleted_at.is_(None),
                )
                .order_by(Node.id)
                .with_for_update()
            ).scalars()
        }
        if len(locked_targets) != len(existing_target_ids):
            raise GraphIntegrityError(
                "an existing target disappeared or crossed project ownership"
            )

        nodes_by_planned_id: dict[uuid.UUID, Node] = {}
        created_node_ids: list[uuid.UUID] = []
        relation_ids: list[uuid.UUID] = []
        merge_operation_ids: list[uuid.UUID] = []
        apply_warnings = list(plan.warnings)

        # Insert every source and immutable evidence before creating graph edges.
        for item in plan.items:
            source = item.source
            node = Node(
                id=source.node_id,
                source_candidate_id=source.candidate_id,
                project_id=plan.project_id,
                source_meeting_id=plan.external_meeting_id,
                source_item_id=source.source_item_id,
                node_type=source.node_type,
                category=source.category,
                title=source.title,
                content=source.content,
                graph_state="UNATTACHED",
                analysis_status="PENDING",
                due_date=source.due_date,
                version=1,
                origin_type="LLM_GENERATED",
                last_actor_type="SYSTEM",
                consistency_status="NORMAL",
            )
            session.add(node)
            session.flush()
            create_node_revision(
                session,
                node=node,
                title=source.title,
                content=source.content,
                node_type=source.node_type,
                category=source.category,
                due_date=source.due_date,
                created_by_type="SYSTEM",
                created_by_id="AUTOMATIC_PIPELINE",
                generation_run_id=plan.generation_run_id,
                evidence_specs=list(source.evidence),
                requires_evidence=True,
            )
            if item.embedding is not None:
                session.add(
                    NodeEmbedding(
                        node_id=node.id,
                        embedding_version=retrieval_settings.embedding_version,
                        embedding_model=retrieval_settings.embedding_model,
                        dimension=retrieval_settings.embedding_dim,
                        embedded_text_hash=hashlib.sha256(
                            _embedding_text(source).encode("utf-8")
                        ).hexdigest(),
                        embedding=item.embedding,
                        status="READY",
                        embedded_at=datetime.now(timezone.utc),
                    )
                )
            nodes_by_planned_id[node.id] = node
            created_node_ids.append(node.id)

        # Canonicalize Decisions first. This preserves Action/Issue parent
        # candidates when their generated Decision is itself merged.
        for item in plan.items:
            if item.source.node_type != "DECISION":
                continue
            operation_id = _apply_planned_merge(
                session,
                plan=plan,
                item=item,
                nodes_by_planned_id=nodes_by_planned_id,
                locked_targets=locked_targets,
                apply_warnings=apply_warnings,
            )
            if operation_id is not None:
                merge_operation_ids.append(operation_id)
            elif item.applied_action != "MERGE":
                # CREATE_NEW/LINK Decision roots are independently valid.
                nodes_by_planned_id[item.source.node_id].graph_state = "ACTIVE"

        # Resolve LINKs after Decision canonicalization so dependent Nodes
        # become ACTIVE only with the final valid structural parent. Relation
        # endpoints still retain the original target ID.
        for item in plan.items:
            if item.applied_action != "LINK" or item.target_node_id is None:
                continue
            source_node = nodes_by_planned_id[item.source.node_id]
            target_node = (
                nodes_by_planned_id.get(item.target_node_id)
                or locked_targets.get(item.target_node_id)
            )
            if target_node is None:
                apply_warnings.append(
                    {
                        "code": "LINK_TARGET_MISSING_AT_APPLY",
                        "candidateId": str(item.source.candidate_id),
                    }
                )
                item.applied_action = "CREATE_NEW"
                item.target_node_id = None
                item.target_node_version = None
                item.relation_type = None
                item.parent_node_id = None
                continue
            if (
                item.target_node_version is not None
                and item.target_node_id not in nodes_by_planned_id
                and target_node.version != item.target_node_version
            ):
                apply_warnings.append(
                    {
                        "code": "LINK_TARGET_VERSION_CHANGED_CREATE_NEW",
                        "candidateId": str(item.source.candidate_id),
                    }
                )
                item.applied_action = "CREATE_NEW"
                item.target_node_id = None
                item.target_node_version = None
                item.relation_type = None
                item.parent_node_id = None
                continue
            canonical = resolve_canonical_node(
                session,
                project_id=plan.project_id,
                node_id=target_node.id,
                for_update=True,
            )
            if item.relation_type == "ATTACHED_TO":
                allowed = (
                    {"DECISION"}
                    if source_node.node_type == "ACTION"
                    else {"DECISION", "ACTION"}
                    if source_node.node_type == "ISSUE"
                    else set()
                )
                if (
                    canonical.graph_state != "ACTIVE"
                    or canonical.node_type not in allowed
                    or canonical.category != source_node.category
                    or canonical.id == source_node.id
                ):
                    apply_warnings.append(
                        {
                            "code": "PARENT_INVALID_AT_APPLY_UNATTACHED",
                            "candidateId": str(item.source.candidate_id),
                        }
                    )
                    item.applied_action = "CREATE_NEW"
                    continue
                relation = _create_or_reactivate_relation(
                    session,
                    project_id=plan.project_id,
                    source_id=source_node.id,
                    target_id=target_node.id,
                    relation_type="ATTACHED_TO",
                    generation_run_id=plan.generation_run_id,
                )
                relation_ids.append(relation.id)
                source_node.parent_id = canonical.id
                source_node.graph_state = "ACTIVE"
            else:
                relation = _create_or_reactivate_relation(
                    session,
                    project_id=plan.project_id,
                    source_id=source_node.id,
                    target_id=target_node.id,
                    relation_type=item.relation_type or "RELATED_TO",
                    generation_run_id=plan.generation_run_id,
                )
                relation_ids.append(relation.id)
                if source_node.node_type == "DECISION":
                    source_node.graph_state = "ACTIVE"

        # Validate every dependent target snapshot before the first member of
        # That separates external stale changes from this Plan's own version
        # increment and keeps one deterministic fold per target.
        merge_operation_ids.extend(
            _apply_dependent_merge_groups(
                session,
                plan=plan,
                nodes_by_planned_id=nodes_by_planned_id,
                locked_targets=locked_targets,
                apply_warnings=apply_warnings,
            )
        )

        # Analysis provenance is written only after every target has been
        # revalidated. No approval Candidate is created.
        for item in plan.items:
            node = nodes_by_planned_id[item.source.node_id]
            _persist_analysis_trace(
                session,
                node=node,
                item=item,
                settings=retrieval_settings,
                provider_model=plan.provider_model,
                pipeline_label=pipeline_label,
            )
            candidate = session.execute(
                select(NodeCandidate)
                .where(
                    NodeCandidate.id == item.source.candidate_id,
                    NodeCandidate.project_id == plan.project_id,
                )
                .with_for_update()
            ).scalar_one()
            candidate.initial_review_node_id = node.id
            candidate.confirmed_node_id = node.id
            candidate.review_status = "APPROVED"
            candidate.reviewed_by = "AUTOMATIC_PIPELINE"
            candidate.reviewed_at = datetime.now(timezone.utc)
            candidate.version += 1

        request = session.execute(
            select(Request)
            .where(
                Request.id == plan.source_request_id,
                Request.project_id == plan.project_id,
            )
            .with_for_update()
        ).scalar_one()
        meeting = session.execute(
            select(Meeting)
            .where(
                Meeting.project_id == plan.project_id,
                Meeting.external_meeting_id == plan.external_meeting_id,
            )
            .with_for_update()
        ).scalar_one()
        status = (
            "COMPLETED_WITH_WARNINGS" if apply_warnings else "COMPLETED"
        )
        summary = {
            "createdNodeIds": [str(value) for value in created_node_ids],
            "mergeOperationIds": [
                str(value) for value in merge_operation_ids
            ],
            "relationIds": [str(value) for value in relation_ids],
            "createdCount": len(created_node_ids),
            "mergedCount": len(merge_operation_ids),
            "relationCount": len(relation_ids),
            "unattachedCount": sum(
                node.graph_state == "UNATTACHED"
                for node in nodes_by_planned_id.values()
            ),
            "warningCount": len(apply_warnings),
        }
        run.status = status
        run.source_request_id = request.id
        run.warnings = apply_warnings or None
        run.result_summary = summary
        run.completed_at = datetime.now(timezone.utc)
        run.updated_at = datetime.now(timezone.utc)
        request.status = "COMPLETED"
        request.completed_at = run.completed_at
        request.warnings = list(request.warnings or []) + [
            warning["code"] for warning in apply_warnings
        ]
        meeting.status = "COMPLETED"
        meeting.updated_at = run.completed_at
        analysis_command = session.execute(
            select(MeetingAnalysisCommand).where(
                MeetingAnalysisCommand.project_id == plan.project_id,
                MeetingAnalysisCommand.meeting_id == plan.external_meeting_id,
            )
        ).scalar_one_or_none()
        if analysis_command is None:
            session.add(
                OutboxEvent(
                event_type="GRAPH_GENERATION_COMPLETED",
                aggregate_type="generation_run",
                aggregate_id=str(run.id),
                project_id=plan.project_id,
                schema_version="auto-graph-v1",
                payload={
                    "generationRunId": str(run.id),
                    "projectId": plan.project_id,
                    "externalMeetingId": plan.external_meeting_id,
                    "status": status,
                    **summary,
                    "warnings": apply_warnings,
                },
                status="PENDING",
                )
            )
        graph_nodes = {
            node.id: node
            for node in [*nodes_by_planned_id.values(), *locked_targets.values()]
        }
        if analysis_command is None:
            _, graph_version = stage_project_graph_changed(
                session,
                project_id=plan.project_id,
                upserted_nodes=list(graph_nodes.values()),
            )
        else:
            # Keep meeting_analysis out of this module's import graph. Snapshot
            # imports the low-level event contract through the pipeline package,
            # so a module-level reverse import would partially initialize both.
            from data_pipeline.meeting_analysis.result_events import (
                stage_project_graph_changed_v3,
            )

            _, _, graph_version = stage_project_graph_changed_v3(
                session,
                command=analysis_command,
            )
        summary["graphVersion"] = graph_version
        run.result_summary = dict(summary)
        if analysis_command is None:
            mark_graph_ready(
                session,
                project_id=plan.project_id,
                external_meeting_id=plan.external_meeting_id,
                graph_version=graph_version,
            )
        session.commit()
        return AutomaticGraphResult(
            generation_run_id=run.id,
            status=status,
            created_node_ids=tuple(created_node_ids),
            merge_operation_ids=tuple(merge_operation_ids),
            relation_ids=tuple(relation_ids),
            warnings=tuple(apply_warnings),
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_automatic_graph(
    session_factory,
    *,
    generation_run_id: uuid.UUID,
    project_id: str,
    external_meeting_id: str,
    candidate_ids: list[str],
    embedding_client: EmbeddingClient,
    b_model_client: BModelClient,
    retrieval_settings: RetrievalSettings | None = None,
    merge_policy: AutoMergePolicy | None = None,
    pipeline_label: str = "automatic-b-model",
) -> AutomaticGraphResult:
    settings = retrieval_settings or load_settings().retrieval
    policy = merge_policy or AutoMergePolicy(
        min_similarity=settings.auto_merge_min_similarity,
        min_margin=settings.auto_merge_min_margin,
    )
    source_request_id, candidates, validation_warnings = (
        _source_request_and_candidates(
            session_factory,
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            candidate_ids=candidate_ids,
        )
    )
    session = session_factory()
    try:
        run = session.execute(
            select(GenerationRun)
            .where(
                GenerationRun.id == generation_run_id,
                GenerationRun.project_id == project_id,
            )
            .with_for_update()
        ).scalar_one()
        run.source_request_id = source_request_id
        run.warnings = validation_warnings or None
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    plan = build_graph_mutation_plan(
        session_factory,
        generation_run_id=generation_run_id,
        project_id=project_id,
        external_meeting_id=external_meeting_id,
        source_request_id=source_request_id,
        candidates=candidates,
        embedding_client=embedding_client,
        b_model_client=b_model_client,
        retrieval_settings=settings,
        merge_policy=policy,
        pipeline_label=pipeline_label,
    )
    if validation_warnings:
        plan = GraphMutationPlan(
            generation_run_id=plan.generation_run_id,
            project_id=plan.project_id,
            external_meeting_id=plan.external_meeting_id,
            source_request_id=plan.source_request_id,
            items=plan.items,
            warnings=tuple(validation_warnings) + plan.warnings,
            provider_model=plan.provider_model,
        )
    _set_run_stage(
        session_factory,
        run_id=generation_run_id,
        project_id=project_id,
        status="VALIDATING",
    )
    return apply_graph_mutation_plan(
        session_factory,
        plan=plan,
        retrieval_settings=settings,
        pipeline_label=pipeline_label,
    )


def run_automatic_meeting(
    session_factory,
    *,
    meeting_input: dict,
    client,
    embedding_client: EmbeddingClient,
    b_model_client: BModelClient,
    pipeline_version: str = "node-generation-v2.2",
    retrieval_settings: RetrievalSettings | None = None,
    merge_policy: AutoMergePolicy | None = None,
    pipeline_label: str = "automatic-b-model",
    force_retry: bool = False,
    meeting_runner=None,
    meeting_summary_generator=None,
    generate_summary: bool = False,
    **meeting_runner_kwargs,
):
    """SQS-facing orchestration wrapper around the existing ``run_meeting``."""

    # ``b_model`` was renamed to ``pipeline_label`` when the execution label
    # stopped doubling as the provider model id. Because the rest of **kwargs is
    # forwarded to ``meeting_runner``, a stale caller would otherwise surface as
    # an unrelated TypeError deep inside run_meeting.
    if "b_model" in meeting_runner_kwargs:
        raise TypeError(
            "run_automatic_meeting no longer accepts 'b_model'; pass "
            "pipeline_label= for the execution label. The provider model comes "
            "from b_model_client.provider_model."
        )

    if meeting_runner is None:
        from .chain import run_meeting as meeting_runner
    if generate_summary and meeting_summary_generator is None:
        raise ValueError(
            "meeting_summary_generator is required when generate_summary is true"
        )

    project_id = canonical_storage_identifier(
        meeting_input["projectId"],
        field="projectId",
    )
    meeting_id = canonical_storage_identifier(
        meeting_input["externalMeetingId"],
        field="externalMeetingId",
    )
    claim = _claim_generation_run(
        session_factory,
        project_id=project_id,
        external_meeting_id=meeting_id,
        recording_hash=_recording_hash(meeting_input),
        pipeline_version=pipeline_version,
        external_request_id=meeting_input.get("requestId"),
        force_retry=force_retry,
    )
    if not claim.claimed and not claim.replayed:
        raise GenerationRunStateError(
            "the same automatic generation input is already processing"
        )
    try:
        result = meeting_runner(
            session_factory,
            meeting_input=meeting_input,
            client=client,
            pipeline_version=pipeline_version,
            force_retry=force_retry,
            **meeting_runner_kwargs,
        )
        if claim.replayed:
            if generate_summary:
                from data_pipeline.meeting_summary import generate_meeting_summary

                generate_meeting_summary(
                    session_factory,
                    project_id=project_id,
                    external_meeting_id=meeting_id,
                    summary_version=1,
                    generator=meeting_summary_generator,
                )
            result.proposal_result = result.proposal_result.model_copy(
                update={
                    "status": "COMPLETED",
                    "outcome": "AUTOMATIC_GRAPH_REPLAYED",
                }
            )
            return result
        proposal = result.proposal_result
        if proposal.status == "FAILED":
            raise GenerationRunStateError(
                "candidate generation failed before automatic graph planning"
            )
        graph_result = run_automatic_graph(
            session_factory,
            generation_run_id=claim.run.id,
            project_id=project_id,
            external_meeting_id=meeting_id,
            candidate_ids=proposal.candidateIds,
            embedding_client=embedding_client,
            b_model_client=b_model_client,
            retrieval_settings=retrieval_settings,
            merge_policy=merge_policy,
            pipeline_label=pipeline_label,
        )
        if generate_summary:
            from data_pipeline.meeting_summary import generate_meeting_summary

            generate_meeting_summary(
                session_factory,
                project_id=project_id,
                external_meeting_id=meeting_id,
                summary_version=1,
                generator=meeting_summary_generator,
            )
        result.proposal_result = proposal.model_copy(
            update={
                "status": "COMPLETED",
                "outcome": graph_result.status,
                "warnings": [
                    str(row.get("code", "WARNING"))
                    for row in graph_result.warnings
                ],
                "detail": {
                    **proposal.detail,
                    "generationRunId": str(graph_result.generation_run_id),
                    "createdNodeIds": [
                        str(value) for value in graph_result.created_node_ids
                    ],
                    "mergeOperationIds": [
                        str(value)
                        for value in graph_result.merge_operation_ids
                    ],
                },
            }
        )
        return result
    except Exception as exc:
        _mark_generation_failed(
            session_factory,
            run_id=claim.run.id,
            project_id=project_id,
            code="AUTOMATIC_GRAPH_FAILED",
            error=exc,
        )
        raise


__all__ = [
    "AutoMergePolicy",
    "AutomaticGraphResult",
    "CandidateSnapshot",
    "GraphMutationPlan",
    "GraphPlanItem",
    "apply_graph_mutation_plan",
    "build_graph_mutation_plan",
    "run_automatic_graph",
    "run_automatic_meeting",
]
