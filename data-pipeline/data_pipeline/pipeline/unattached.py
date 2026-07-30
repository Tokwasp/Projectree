"""Application services for editing first-reviewed UNATTACHED Nodes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from pydantic import ValidationError

from data_pipeline.contracts import (
    CandidateEvidenceView,
    GraphState,
    NodeType,
    UnattachedEvidenceInput,
    UnattachedNodeEditResult,
    UnattachedNodeView,
    default_lifecycle_status,
)
from data_pipeline.storage.evidence import (
    build_evidence_key,
    upsert_node_evidence,
)
from data_pipeline.storage.models import (
    Category,
    GraphChangeEvent,
    Node,
    NodeAnalysisRun,
    NodeEvidence,
    TranscriptSegment,
)
from data_pipeline.validation import SegmentInfo, resolve_item_evidence

from .errors import (
    NodeNotFoundError,
    NodeStateError,
    NodeValidationError,
    NodeVersionConflict,
)

_UNSET = object()
_NODE_TYPES = frozenset(value.value for value in NodeType)


def _uuid(value: str | uuid.UUID) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise NodeValidationError("node_id must be a UUID") from exc


def _view(node: Node) -> UnattachedNodeView:
    return UnattachedNodeView(
        node_id=str(node.id),
        project_id=node.project_id,
        node_type=NodeType(node.node_type),
        category=node.category,
        title=node.title,
        content=node.content,
        graph_state=GraphState(node.graph_state),
        analysis_status=node.analysis_status,
        analysis_input_hash=node.analysis_input_hash,
        current_analysis_run_id=(
            str(node.current_analysis_run_id)
            if node.current_analysis_run_id is not None
            else None
        ),
        version=node.version,
        evidence=[
            CandidateEvidenceView(
                segment_id=evidence.segment_id,
                quote=evidence.quote,
                quote_start=evidence.quote_start,
                quote_end=evidence.quote_end,
                evidence_type=evidence.evidence_type,
                source_meeting_id=evidence.source_meeting_id,
            )
            for evidence in sorted(
                node.evidence,
                key=lambda row: (
                    row.source_meeting_id or "",
                    row.segment_id,
                    row.quote_start if row.quote_start is not None else -1,
                    row.evidence_key,
                ),
            )
        ],
    )


def _snapshot(node: Node) -> dict[str, Any]:
    return {
        "nodeId": str(node.id),
        "nodeType": node.node_type,
        "category": node.category,
        "title": node.title,
        "content": node.content,
        "graphState": node.graph_state,
        "analysisStatus": node.analysis_status,
        "analysisInputHash": node.analysis_input_hash,
        "currentAnalysisRunId": (
            str(node.current_analysis_run_id)
            if node.current_analysis_run_id is not None
            else None
        ),
        "version": node.version,
        "evidenceKeys": sorted(evidence.evidence_key for evidence in node.evidence),
    }


def _resolve_evidence(
    session,
    *,
    node: Node,
    evidence_values: list[dict | UnattachedEvidenceInput],
) -> list[dict[str, Any]]:
    resolved_values: list[dict[str, Any]] = []
    for raw in evidence_values:
        try:
            value = (
                raw
                if isinstance(raw, UnattachedEvidenceInput)
                else UnattachedEvidenceInput.model_validate(raw)
            )
        except ValidationError as exc:
            raise NodeValidationError(f"invalid evidence: {exc}") from exc
        source_meeting_id = value.sourceMeetingId or node.source_meeting_id
        segment = session.execute(
            select(TranscriptSegment).where(
                TranscriptSegment.project_id == node.project_id,
                TranscriptSegment.external_meeting_id == source_meeting_id,
                TranscriptSegment.segment_id == value.segmentId,
            )
        ).scalar_one_or_none()
        if segment is None:
            raise NodeValidationError(
                f"missing transcript segment: {source_meeting_id}/{value.segmentId}"
            )

        quote = value.quote.strip()
        resolution = resolve_item_evidence(
            {
                "id": str(node.id),
                "evidence": [
                    {
                        "segmentId": value.segmentId,
                        "quote": quote,
                    }
                ],
            },
            {
                value.segmentId: SegmentInfo(
                    text=segment.normalized_text or segment.text,
                    start_ms=segment.start_ms,
                )
            },
        )
        if not resolution.valid:
            raise NodeValidationError("; ".join(resolution.problems))
        resolved = resolution.resolved[0]
        current = {
            "segment_id": value.segmentId,
            "quote": quote,
            "quote_start": resolved.char_start,
            "quote_end": resolved.char_end,
            "evidence_type": "MEETING",
            "source_meeting_id": source_meeting_id,
        }
        current["evidence_key"] = build_evidence_key(**current)
        resolved_values.append(current)
    return resolved_values


def _same_requested_state(
    node: Node,
    *,
    scalar_values: dict[str, Any],
    resolved_evidence: list[dict[str, Any]] | None,
) -> bool:
    if any(getattr(node, key) != value for key, value in scalar_values.items()):
        return False
    if resolved_evidence is None:
        return True
    requested_keys = {value["evidence_key"] for value in resolved_evidence}
    current_keys = {evidence.evidence_key for evidence in node.evidence}
    return requested_keys == current_keys


def edit_unattached_node(
    session_factory,
    node_id: str | uuid.UUID,
    *,
    actor_id: str,
    expected_version: int,
    node_type: str | object = _UNSET,
    category: str | object = _UNSET,
    title: str | object = _UNSET,
    content: str | object = _UNSET,
    evidence: list[dict | UnattachedEvidenceInput] | object = _UNSET,
) -> UnattachedNodeEditResult:
    """Edit Retrieval inputs and invalidate every prior analysis atomically."""

    if all(
        value is _UNSET
        for value in (node_type, category, title, content, evidence)
    ):
        raise NodeValidationError("at least one editable field is required")

    parsed_id = _uuid(node_id)
    session = session_factory()
    try:
        node = (
            session.execute(
                select(Node)
                .options(selectinload(Node.evidence))
                .where(Node.id == parsed_id)
                .with_for_update()
            )
            .scalars()
            .unique()
            .one_or_none()
        )
        if node is None:
            raise NodeNotFoundError(f"node not found: {node_id}")
        if (
            node.graph_state != GraphState.UNATTACHED.value
            or node.merged_into_node_id is not None
        ):
            raise NodeStateError(
                "only non-merged UNATTACHED nodes can be edited"
            )

        scalar_values: dict[str, Any] = {}
        if node_type is not _UNSET:
            normalized_type = (
                node_type.value
                if isinstance(node_type, NodeType)
                else str(node_type)
            )
            if normalized_type not in _NODE_TYPES:
                raise NodeValidationError(f"invalid node_type: {normalized_type}")
            scalar_values["node_type"] = normalized_type
            if normalized_type != node.node_type:
                scalar_values["lifecycle_status"] = default_lifecycle_status(
                    normalized_type
                )
        if category is not _UNSET:
            normalized_category = str(category)
            category_row = session.get(Category, normalized_category)
            if category_row is None or not category_row.is_active:
                raise NodeValidationError(
                    f"category is not active: {normalized_category}"
                )
            scalar_values["category"] = normalized_category
        if title is not _UNSET:
            if title is None:
                raise NodeValidationError("title must not be null")
            scalar_values["title"] = str(title)
        if content is not _UNSET:
            if content is None:
                raise NodeValidationError("content must not be null")
            scalar_values["content"] = str(content)

        if evidence is not _UNSET and not evidence:
            raise NodeValidationError("evidence must not be empty")
        resolved_evidence = (
            None
            if evidence is _UNSET
            else _resolve_evidence(
                session,
                node=node,
                evidence_values=list(evidence),
            )
        )
        is_same = _same_requested_state(
            node,
            scalar_values=scalar_values,
            resolved_evidence=resolved_evidence,
        )
        if node.version != expected_version:
            if is_same:
                session.rollback()
                return UnattachedNodeEditResult(
                    node=_view(node),
                    analysis_invalidated=False,
                )
            raise NodeVersionConflict(
                str(node.id),
                expected_version,
                node.version,
            )
        if is_same:
            session.rollback()
            return UnattachedNodeEditResult(
                node=_view(node),
                analysis_invalidated=False,
            )

        before = _snapshot(node)
        current_run = (
            session.get(
                NodeAnalysisRun,
                node.current_analysis_run_id,
                with_for_update=True,
            )
            if node.current_analysis_run_id is not None
            else None
        )
        if current_run is not None and current_run.status in {
            "PENDING",
            "RUNNING",
            "COMPLETED",
        }:
            current_run.status = "SUPERSEDED"
            current_run.completed_at = datetime.now(timezone.utc)
        for key, value in scalar_values.items():
            setattr(node, key, value)

        if resolved_evidence is not None:
            requested_keys = {
                value["evidence_key"] for value in resolved_evidence
            }
            session.execute(
                delete(NodeEvidence).where(
                    NodeEvidence.node_id == node.id,
                    NodeEvidence.evidence_key.not_in(requested_keys),
                )
            )
            for value in resolved_evidence:
                upsert_node_evidence(
                    session,
                    node_id=node.id,
                    segment_id=value["segment_id"],
                    quote=value["quote"],
                    quote_start=value["quote_start"],
                    quote_end=value["quote_end"],
                    evidence_type=value["evidence_type"],
                    source_meeting_id=value["source_meeting_id"],
                )
            session.expire(node, ["evidence"])

        node.version += 1
        node.analysis_status = "STALE"
        node.analysis_input_hash = None
        session.flush()
        session.refresh(node)
        after = _snapshot(node)
        session.add(
            GraphChangeEvent(
                project_id=node.project_id,
                node_id=node.id,
                item_id=node.source_item_id,
                change_type="UPDATE",
                actor_type="USER",
                before=before,
                after=after,
                detail={
                    "stage": "UNATTACHED_EDIT",
                    "actorId": actor_id,
                    "analysisInvalidated": True,
                },
            )
        )
        session.commit()
        return UnattachedNodeEditResult(
            node=_view(node),
            analysis_invalidated=True,
        )
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
