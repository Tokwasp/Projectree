"""Step 4B application services for reviewing and confirming candidates."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from data_pipeline.contracts import (
    CandidateEvidenceView,
    CandidateReviewResult,
    CandidateView,
    GraphState,
    default_lifecycle_status,
)
from data_pipeline.storage.models import (
    CandidateReviewEvent,
    Category,
    GraphChangeEvent,
    Meeting,
    Node,
    NodeCandidate,
    Relation,
    Request,
)
from data_pipeline.storage.evidence import upsert_node_evidence

from .errors import (
    CandidateNotFoundError,
    CandidateReviewError,
    CandidateStateError,
    CandidateValidationError,
    CandidateVersionConflict,
)
from .repository import get_candidate_for_review, query_candidates_for_review

_UNSET = object()
_NODE_TYPES = frozenset({"DECISION", "ACTION", "ISSUE"})
_DISPOSITIONS = frozenset(
    {"NEW_DECISION", "ATTACH", "UNATTACHED", "MINUTES_ONLY"}
)
_PARENT_MODES = frozenset({"INHERIT", "CANDIDATE", "NODE", "NONE"})


def _uuid(value: str | uuid.UUID, *, field: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise CandidateValidationError(f"{field} must be a UUID") from exc


def _effective_parent(
    candidate: NodeCandidate,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    mode = candidate.reviewed_parent_mode or "INHERIT"
    if mode == "INHERIT":
        return (
            candidate.suggested_parent_candidate_id,
            candidate.suggested_parent_node_id,
        )
    if mode == "NONE":
        return None, None
    if mode == "CANDIDATE":
        return candidate.reviewed_parent_candidate_id, None
    if mode == "NODE":
        return None, candidate.reviewed_parent_node_id
    raise CandidateValidationError(f"invalid reviewed_parent_mode: {mode}")


def _effective(candidate: NodeCandidate) -> dict[str, Any]:
    parent_candidate_id, parent_node_id = _effective_parent(candidate)
    return {
        "type": candidate.reviewed_node_type or candidate.suggested_node_type,
        "category": candidate.reviewed_category or candidate.suggested_category,
        "title": (
            candidate.reviewed_title
            if candidate.reviewed_title is not None
            else candidate.suggested_title
        ),
        "content": (
            candidate.reviewed_content
            if candidate.reviewed_content is not None
            else candidate.suggested_content
        ),
        "disposition": (
            candidate.reviewed_disposition
            or candidate.suggested_disposition
        ),
        "parent_candidate_id": parent_candidate_id,
        "parent_node_id": parent_node_id,
    }


def _candidate_view(candidate: NodeCandidate) -> CandidateView:
    effective = _effective(candidate)
    return CandidateView(
        candidate_id=str(candidate.id),
        request_id=str(candidate.request_id),
        source_item_id=candidate.source_item_id,
        project_id=candidate.project_id,
        external_meeting_id=candidate.external_meeting_id,
        suggested_type=candidate.suggested_node_type,
        suggested_category=candidate.suggested_category,
        suggested_title=candidate.suggested_title,
        suggested_content=candidate.suggested_content,
        suggested_disposition=candidate.suggested_disposition,
        suggested_reason=candidate.suggested_reason,
        suggested_parent_candidate_id=(
            str(candidate.suggested_parent_candidate_id)
            if candidate.suggested_parent_candidate_id
            else None
        ),
        suggested_parent_node_id=(
            str(candidate.suggested_parent_node_id)
            if candidate.suggested_parent_node_id
            else None
        ),
        reviewed_type=candidate.reviewed_node_type,
        reviewed_category=candidate.reviewed_category,
        reviewed_title=candidate.reviewed_title,
        reviewed_content=candidate.reviewed_content,
        reviewed_disposition=candidate.reviewed_disposition,
        reviewed_parent_mode=candidate.reviewed_parent_mode or "INHERIT",
        reviewed_parent_candidate_id=(
            str(candidate.reviewed_parent_candidate_id)
            if candidate.reviewed_parent_candidate_id
            else None
        ),
        reviewed_parent_node_id=(
            str(candidate.reviewed_parent_node_id)
            if candidate.reviewed_parent_node_id
            else None
        ),
        effective_type=effective["type"],
        effective_category=effective["category"],
        effective_title=effective["title"],
        effective_content=effective["content"],
        effective_disposition=effective["disposition"],
        effective_parent_candidate_id=(
            str(effective["parent_candidate_id"])
            if effective["parent_candidate_id"]
            else None
        ),
        effective_parent_node_id=(
            str(effective["parent_node_id"])
            if effective["parent_node_id"]
            else None
        ),
        review_status=candidate.review_status,
        version=candidate.version,
        initial_review_node_id=(
            str(candidate.initial_review_node_id)
            if candidate.initial_review_node_id
            else None
        ),
        confirmed_node_id=(
            str(candidate.confirmed_node_id)
            if candidate.confirmed_node_id
            else None
        ),
        evidence=[
            CandidateEvidenceView(
                segment_id=evidence.segment_id,
                quote=evidence.quote,
                quote_start=evidence.quote_start,
                quote_end=evidence.quote_end,
                evidence_type=evidence.evidence_type,
                source_meeting_id=evidence.source_meeting_id,
            )
            for evidence in candidate.evidence
        ],
        created_at=candidate.created_at,
        reviewed_at=candidate.reviewed_at,
        reviewed_by=candidate.reviewed_by,
    )


def _audit_snapshot(candidate: NodeCandidate) -> dict:
    effective = _effective(candidate)
    return {
        "reviewStatus": candidate.review_status,
        "version": candidate.version,
        "reviewedType": candidate.reviewed_node_type,
        "reviewedCategory": candidate.reviewed_category,
        "reviewedTitle": candidate.reviewed_title,
        "reviewedContent": candidate.reviewed_content,
        "reviewedDisposition": candidate.reviewed_disposition,
        "reviewedParentMode": candidate.reviewed_parent_mode or "INHERIT",
        "reviewedParentCandidateId": (
            str(candidate.reviewed_parent_candidate_id)
            if candidate.reviewed_parent_candidate_id
            else None
        ),
        "reviewedParentNodeId": (
            str(candidate.reviewed_parent_node_id)
            if candidate.reviewed_parent_node_id
            else None
        ),
        "effectiveType": effective["type"],
        "effectiveCategory": effective["category"],
        "effectiveTitle": effective["title"],
        "effectiveContent": effective["content"],
        "effectiveDisposition": effective["disposition"],
        "effectiveParentCandidateId": (
            str(effective["parent_candidate_id"])
            if effective["parent_candidate_id"]
            else None
        ),
        "effectiveParentNodeId": (
            str(effective["parent_node_id"])
            if effective["parent_node_id"]
            else None
        ),
        "confirmedNodeId": (
            str(candidate.confirmed_node_id)
            if candidate.confirmed_node_id
            else None
        ),
        "initialReviewNodeId": (
            str(candidate.initial_review_node_id)
            if candidate.initial_review_node_id
            else None
        ),
    }


def _add_audit(
    session,
    candidate: NodeCandidate,
    *,
    actor_id: str,
    action: str,
    before: dict,
) -> None:
    session.add(
        CandidateReviewEvent(
            candidate_id=candidate.id,
            request_id=candidate.request_id,
            actor_id=actor_id,
            action=action,
            before_json=before,
            after_json=_audit_snapshot(candidate),
        )
    )


def _update_review_statuses(session, request_ids: set[uuid.UUID]) -> None:
    meeting_keys: set[tuple[str, str]] = set()
    for request_id in sorted(request_ids, key=str):
        request = session.execute(
            select(Request).where(Request.id == request_id).with_for_update()
        ).scalar_one_or_none()
        if request is None:
            continue
        pending = session.scalar(
            select(func.count())
            .select_from(NodeCandidate)
            .where(
                NodeCandidate.request_id == request_id,
                NodeCandidate.review_status == "PENDING",
            )
        )
        request.status = "REVIEW_PENDING" if pending else "REVIEW_COMPLETED"
        meeting_keys.add((request.project_id, request.external_meeting_id))

    for project_id, meeting_id in sorted(meeting_keys):
        pending = session.scalar(
            select(func.count())
            .select_from(NodeCandidate)
            .where(
                NodeCandidate.project_id == project_id,
                NodeCandidate.external_meeting_id == meeting_id,
                NodeCandidate.review_status == "PENDING",
            )
        )
        meeting = session.execute(
            select(Meeting).where(
                Meeting.project_id == project_id,
                Meeting.external_meeting_id == meeting_id,
            ).with_for_update()
        ).scalar_one_or_none()
        if meeting is not None:
            meeting.status = "REVIEW_PENDING" if pending else "REVIEW_COMPLETED"


def list_candidates(
    session_factory,
    *,
    project_id: str,
    external_meeting_id: str | None = None,
    request_id: str | uuid.UUID | None = None,
    review_status: str | None = None,
    node_type: str | None = None,
    suggested_disposition: str | None = None,
) -> list[CandidateView]:
    if review_status is not None and review_status not in {
        "PENDING",
        "APPROVED",
        "REJECTED",
    }:
        raise CandidateValidationError(f"invalid review_status: {review_status}")
    if node_type is not None and node_type not in _NODE_TYPES | {"UNKNOWN"}:
        raise CandidateValidationError(f"invalid node_type: {node_type}")
    with session_factory() as session:
        candidates = query_candidates_for_review(
            session,
            project_id=project_id,
            external_meeting_id=external_meeting_id,
            request_id=request_id,
            review_status=review_status,
            suggested_disposition=suggested_disposition,
        )
        if node_type is not None:
            candidates = [
                candidate
                for candidate in candidates
                if _effective(candidate)["type"] == node_type
            ]
        return [_candidate_view(candidate) for candidate in candidates]


def get_candidate(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    project_id: str | None = None,
) -> CandidateView:
    with session_factory() as session:
        candidate = get_candidate_for_review(session, candidate_id)
        if candidate is None or (
            project_id is not None and candidate.project_id != project_id
        ):
            raise CandidateNotFoundError(f"candidate not found: {candidate_id}")
        return _candidate_view(candidate)


def _normalized_edit_values(
    *,
    node_type: str | object,
    category: str | object,
    title: str | object,
    content: str | object,
    disposition: str | object,
    parent_mode: str | None,
    parent_candidate_id: str | uuid.UUID | None,
    parent_node_id: str | uuid.UUID | None,
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if node_type is not _UNSET:
        normalized_type = str(node_type)
        if normalized_type not in _NODE_TYPES:
            raise CandidateValidationError(f"invalid node_type: {normalized_type}")
        values["reviewed_node_type"] = normalized_type
    if category is not _UNSET:
        normalized_category = str(category)
        if not normalized_category:
            raise CandidateValidationError("category must not be empty")
        values["reviewed_category"] = normalized_category
    if title is not _UNSET:
        values["reviewed_title"] = str(title)
    if content is not _UNSET:
        values["reviewed_content"] = str(content)
    if disposition is not _UNSET:
        normalized_disposition = str(disposition)
        if normalized_disposition not in _DISPOSITIONS:
            raise CandidateValidationError(
                f"invalid disposition: {normalized_disposition}"
            )
        values["reviewed_disposition"] = normalized_disposition
    if parent_mode is not None:
        normalized_mode = parent_mode.upper()
        if normalized_mode not in _PARENT_MODES:
            raise CandidateValidationError(f"invalid parent_mode: {parent_mode}")
        values["reviewed_parent_mode"] = normalized_mode
        values["reviewed_parent_candidate_id"] = None
        values["reviewed_parent_node_id"] = None
        if normalized_mode == "CANDIDATE":
            if parent_candidate_id is None or parent_node_id is not None:
                raise CandidateValidationError(
                    "CANDIDATE parent mode requires only parent_candidate_id"
                )
            values["reviewed_parent_candidate_id"] = _uuid(
                parent_candidate_id, field="parent_candidate_id"
            )
        elif normalized_mode == "NODE":
            if parent_node_id is None or parent_candidate_id is not None:
                raise CandidateValidationError(
                    "NODE parent mode requires only parent_node_id"
                )
            values["reviewed_parent_node_id"] = _uuid(
                parent_node_id, field="parent_node_id"
            )
        elif parent_candidate_id is not None or parent_node_id is not None:
            raise CandidateValidationError(
                f"{normalized_mode} parent mode does not accept a parent id"
            )
    elif parent_candidate_id is not None or parent_node_id is not None:
        raise CandidateValidationError("parent_mode is required when changing parent")
    return values


def edit_candidate(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    actor_id: str,
    expected_version: int,
    node_type: str | object = _UNSET,
    category: str | object = _UNSET,
    title: str | object = _UNSET,
    content: str | object = _UNSET,
    disposition: str | object = _UNSET,
    parent_mode: str | None = None,
    parent_candidate_id: str | uuid.UUID | None = None,
    parent_node_id: str | uuid.UUID | None = None,
) -> CandidateReviewResult:
    values = _normalized_edit_values(
        node_type=node_type,
        category=category,
        title=title,
        content=content,
        disposition=disposition,
        parent_mode=parent_mode,
        parent_candidate_id=parent_candidate_id,
        parent_node_id=parent_node_id,
    )
    session = session_factory()
    try:
        candidate = get_candidate_for_review(session, candidate_id)
        if candidate is None:
            raise CandidateNotFoundError(f"candidate not found: {candidate_id}")
        if candidate.review_status != "PENDING":
            raise CandidateStateError(
                f"only PENDING candidates can be edited: {candidate.review_status}"
            )
        reviewed_category = values.get("reviewed_category")
        if reviewed_category is not None:
            category_row = session.get(Category, reviewed_category)
            if category_row is None or not category_row.is_active:
                raise CandidateValidationError(
                    f"category is not active: {reviewed_category}"
                )
        is_same = all(getattr(candidate, key) == value for key, value in values.items())
        if candidate.version != expected_version:
            if is_same:
                session.rollback()
                return CandidateReviewResult(candidates=[_candidate_view(candidate)])
            raise CandidateVersionConflict(
                str(candidate.id), expected_version, candidate.version
            )
        if is_same:
            session.rollback()
            return CandidateReviewResult(candidates=[_candidate_view(candidate)])

        reviewed_parent_candidate_id = values.get("reviewed_parent_candidate_id")
        if reviewed_parent_candidate_id is not None:
            if reviewed_parent_candidate_id == candidate.id:
                raise CandidateValidationError("candidate cannot be its own parent")
            if session.get(NodeCandidate, reviewed_parent_candidate_id) is None:
                raise CandidateValidationError("parent candidate does not exist")
        reviewed_parent_node_id = values.get("reviewed_parent_node_id")
        if (
            reviewed_parent_node_id is not None
            and session.get(Node, reviewed_parent_node_id) is None
        ):
            raise CandidateValidationError("parent node does not exist")
        before = _audit_snapshot(candidate)
        reviewed_at = datetime.now(timezone.utc)
        result = session.execute(
            update(NodeCandidate)
            .where(
                NodeCandidate.id == candidate.id,
                NodeCandidate.version == expected_version,
                NodeCandidate.review_status == "PENDING",
            )
            .values(
                **values,
                version=expected_version + 1,
                reviewed_by=actor_id,
                reviewed_at=reviewed_at,
                updated_at=reviewed_at,
            )
        )
        if result.rowcount != 1:
            session.rollback()
            current = get_candidate_for_review(session, candidate_id)
            if current is None:
                raise CandidateNotFoundError(f"candidate not found: {candidate_id}")
            if current.review_status != "PENDING":
                raise CandidateStateError(
                    f"only PENDING candidates can be edited: {current.review_status}"
                )
            if all(getattr(current, key) == value for key, value in values.items()):
                return CandidateReviewResult(candidates=[_candidate_view(current)])
            raise CandidateVersionConflict(
                str(current.id), expected_version, current.version
            )
        session.refresh(candidate)
        _add_audit(
            session,
            candidate,
            actor_id=actor_id,
            action="EDIT",
            before=before,
        )
        session.commit()
        return CandidateReviewResult(candidates=[_candidate_view(candidate)])
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reject_candidate(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    actor_id: str,
    expected_version: int | None = None,
) -> CandidateReviewResult:
    session = session_factory()
    try:
        candidate = get_candidate_for_review(session, candidate_id, for_update=True)
        if candidate is None:
            raise CandidateNotFoundError(f"candidate not found: {candidate_id}")
        if candidate.review_status == "REJECTED":
            session.rollback()
            return CandidateReviewResult(candidates=[_candidate_view(candidate)])
        if candidate.review_status == "APPROVED":
            raise CandidateStateError("APPROVED candidate cannot be rejected")
        if expected_version is not None and candidate.version != expected_version:
            raise CandidateVersionConflict(
                str(candidate.id), expected_version, candidate.version
            )

        before = _audit_snapshot(candidate)
        candidate.review_status = "REJECTED"
        candidate.version += 1
        candidate.reviewed_by = actor_id
        candidate.reviewed_at = datetime.now(timezone.utc)
        _add_audit(
            session,
            candidate,
            actor_id=actor_id,
            action="REJECT",
            before=before,
        )
        _update_review_statuses(session, {candidate.request_id})
        session.commit()
        return CandidateReviewResult(candidates=[_candidate_view(candidate)])
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _validate_candidate_shape(candidate: NodeCandidate, effective: dict[str, Any]) -> None:
    node_type = effective["type"]
    disposition = effective["disposition"]
    if node_type not in _NODE_TYPES:
        raise CandidateValidationError(
            f"candidate {candidate.id} requires a valid reviewed node type"
        )
    if disposition not in _DISPOSITIONS:
        raise CandidateValidationError(
            f"candidate {candidate.id} has invalid disposition {disposition}"
        )
    if disposition == "NEW_DECISION" and node_type != "DECISION":
        raise CandidateValidationError("NEW_DECISION requires DECISION type")
    if disposition in {"ATTACH", "UNATTACHED"} and node_type not in {
        "ACTION",
        "ISSUE",
    }:
        raise CandidateValidationError(
            f"{disposition} requires ACTION or ISSUE type"
        )
    parent_count = sum(
        value is not None
        for value in (
            effective["parent_candidate_id"],
            effective["parent_node_id"],
        )
    )
    if disposition == "ATTACH" and parent_count != 1:
        raise CandidateValidationError("ATTACH requires exactly one effective parent")
    if disposition in {"NEW_DECISION", "UNATTACHED"} and parent_count:
        raise CandidateValidationError(
            f"{disposition} must not have an effective parent"
        )


def _parent_type_allowed(child_type: str, parent_type: str) -> bool:
    # Existing domain contract explicitly supports Issue -> Action in addition
    # to the default Action/Issue -> Decision relation.
    return (
        child_type == "ACTION"
        and parent_type == "DECISION"
        or child_type == "ISSUE"
        and parent_type in {"DECISION", "ACTION"}
    )


def _ordered_candidates(
    candidates: list[NodeCandidate],
    effective_by_id: dict[uuid.UUID, dict[str, Any]],
) -> list[NodeCandidate]:
    by_id = {candidate.id: candidate for candidate in candidates}
    dependencies: dict[uuid.UUID, set[uuid.UUID]] = {
        candidate.id: set() for candidate in candidates
    }
    for candidate in candidates:
        effective = effective_by_id[candidate.id]
        parent_id = effective["parent_candidate_id"]
        if effective["disposition"] == "ATTACH" and parent_id in by_id:
            dependencies[candidate.id].add(parent_id)

    ordered: list[NodeCandidate] = []
    emitted: set[uuid.UUID] = set()
    while len(ordered) < len(candidates):
        ready = [
            candidate
            for candidate in candidates
            if candidate.id not in emitted
            and dependencies[candidate.id] <= emitted
        ]
        if not ready:
            raise CandidateValidationError("candidate parent dependency cycle")
        ready.sort(key=lambda candidate: (candidate.created_at, str(candidate.id)))
        for candidate in ready:
            ordered.append(candidate)
            emitted.add(candidate.id)
    return ordered


def _node_snapshot(node: Node) -> dict:
    return {
        "nodeId": str(node.id),
        "nodeType": node.node_type,
        "category": node.category,
        "title": node.title,
        "content": node.content,
        "parentId": str(node.parent_id) if node.parent_id else None,
        "graphState": node.graph_state,
        "analysisStatus": node.analysis_status,
        "mergedIntoNodeId": (
            str(node.merged_into_node_id)
            if node.merged_into_node_id
            else None
        ),
        "lifecycleStatus": node.lifecycle_status,
        "version": node.version,
    }


def _validate_initial_review_shape(
    candidate: NodeCandidate,
    effective: dict[str, Any],
) -> None:
    """Validate reviewed content without applying suggested graph relations."""

    disposition = effective["disposition"]
    if disposition not in _DISPOSITIONS:
        raise CandidateValidationError(
            f"candidate {candidate.id} has invalid disposition {disposition}"
        )
    if disposition == "MINUTES_ONLY":
        return
    if effective["type"] not in _NODE_TYPES:
        raise CandidateValidationError(
            f"candidate {candidate.id} requires a valid reviewed node type"
        )


def complete_initial_review(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    actor_id: str,
    expected_version: int | None = None,
) -> CandidateReviewResult:
    """Materialize reviewed Candidate content as an UNATTACHED Node only.

    This is the new first-review boundary.  It deliberately ignores suggested
    parent links and never creates a Relation or an ACTIVE Node.
    """

    session = session_factory()
    try:
        candidate = get_candidate_for_review(
            session,
            candidate_id,
            for_update=True,
        )
        if candidate is None:
            raise CandidateNotFoundError(f"candidate not found: {candidate_id}")
        if candidate.review_status == "APPROVED":
            session.rollback()
            return CandidateReviewResult(candidates=[_candidate_view(candidate)])
        if candidate.review_status == "REJECTED":
            raise CandidateStateError("REJECTED candidate cannot complete review")
        if expected_version is not None and candidate.version != expected_version:
            raise CandidateVersionConflict(
                str(candidate.id),
                expected_version,
                candidate.version,
            )

        effective = _effective(candidate)
        _validate_initial_review_shape(candidate, effective)
        before = _audit_snapshot(candidate)
        reviewed_at = datetime.now(timezone.utc)
        node: Node | None = None

        if effective["disposition"] != "MINUTES_ONLY":
            category = effective["category"]
            category_row = session.get(Category, category) if category else None
            if category_row is None or not category_row.is_active:
                raise CandidateValidationError(
                    f"candidate {candidate.id} has no active category"
                )

            node = Node(
                source_candidate_id=candidate.id,
                project_id=candidate.project_id,
                source_meeting_id=candidate.external_meeting_id,
                source_item_id=candidate.source_item_id,
                node_type=effective["type"],
                category=category,
                title=effective["title"],
                content=effective["content"],
                parent_id=None,
                graph_state=GraphState.UNATTACHED.value,
                analysis_status="PENDING",
                lifecycle_status=default_lifecycle_status(effective["type"]),
                initial_reviewed_by=actor_id,
                initial_reviewed_at=reviewed_at,
            )
            session.add(node)
            session.flush()
            candidate.initial_review_node_id = node.id

            for evidence in candidate.evidence:
                upsert_node_evidence(
                    session,
                    node_id=node.id,
                    segment_id=evidence.segment_id,
                    quote=evidence.quote,
                    quote_start=evidence.quote_start,
                    quote_end=evidence.quote_end,
                    evidence_type=evidence.evidence_type,
                    source_meeting_id=evidence.source_meeting_id,
                )

            request = session.get(Request, candidate.request_id)
            session.add(
                GraphChangeEvent(
                    project_id=candidate.project_id,
                    request_id=(
                        request.external_request_id
                        if request is not None
                        else None
                    ),
                    node_id=node.id,
                    item_id=candidate.source_item_id,
                    change_type="CREATE",
                    actor_type="USER",
                    before=None,
                    after=_node_snapshot(node),
                    detail={
                        "stage": "INITIAL_REVIEW",
                        "actorId": actor_id,
                    },
                )
            )

        candidate.review_status = "APPROVED"
        candidate.version += 1
        candidate.reviewed_by = actor_id
        candidate.reviewed_at = reviewed_at
        _add_audit(
            session,
            candidate,
            actor_id=actor_id,
            action="APPROVE",
            before=before,
        )
        _update_review_statuses(session, {candidate.request_id})
        session.commit()

        return CandidateReviewResult(
            candidates=[_candidate_view(candidate)],
            created_node_ids=[str(node.id)] if node is not None else [],
        )
    except IntegrityError as exc:
        session.rollback()
        current = get_candidate_for_review(session, candidate_id)
        if current is not None and current.review_status == "APPROVED":
            return CandidateReviewResult(candidates=[_candidate_view(current)])
        raise CandidateReviewError(
            "initial review integrity conflict"
        ) from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def bulk_approve_candidates(
    session_factory,
    candidate_ids: list[str | uuid.UUID],
    *,
    actor_id: str,
    expected_versions: dict[str, int] | None = None,
) -> CandidateReviewResult:
    """Legacy combined approval path kept only for existing callers.

    New flows must call ``complete_initial_review`` and must not use this
    function to bypass Retrieval and the separate final-approval services.
    """

    parsed_ids = list(dict.fromkeys(_uuid(value, field="candidate_id") for value in candidate_ids))
    if not parsed_ids:
        return CandidateReviewResult()

    session = session_factory()
    try:
        selected = list(
            session.execute(
                select(NodeCandidate)
                .options(selectinload(NodeCandidate.evidence))
                .where(NodeCandidate.id.in_(parsed_ids))
                .order_by(NodeCandidate.id)
                .with_for_update()
            )
            .scalars()
            .unique()
        )
        by_id = {candidate.id: candidate for candidate in selected}
        missing = [str(candidate_id) for candidate_id in parsed_ids if candidate_id not in by_id]
        if missing:
            raise CandidateNotFoundError(f"candidates not found: {missing}")
        ordered_input = [by_id[candidate_id] for candidate_id in parsed_ids]
        projects = {candidate.project_id for candidate in ordered_input}
        if len(projects) != 1:
            raise CandidateValidationError(
                "bulk approval candidates must belong to one project"
            )

        expected_versions = expected_versions or {}
        pending: list[NodeCandidate] = []
        for candidate in ordered_input:
            if candidate.review_status == "APPROVED":
                continue
            if candidate.review_status == "REJECTED":
                raise CandidateStateError("REJECTED candidate cannot be approved")
            expected = expected_versions.get(str(candidate.id))
            if expected is not None and candidate.version != expected:
                raise CandidateVersionConflict(
                    str(candidate.id), expected, candidate.version
                )
            pending.append(candidate)

        if not pending:
            session.rollback()
            return CandidateReviewResult(
                candidates=[_candidate_view(candidate) for candidate in ordered_input]
            )

        effective_by_id = {
            candidate.id: _effective(candidate) for candidate in pending
        }
        for candidate in pending:
            _validate_candidate_shape(candidate, effective_by_id[candidate.id])
        ordered = _ordered_candidates(pending, effective_by_id)

        parent_candidate_ids = {
            effective["parent_candidate_id"]
            for effective in effective_by_id.values()
            if effective["parent_candidate_id"] is not None
        }
        parent_candidates = list(
            session.execute(
                select(NodeCandidate)
                .options(selectinload(NodeCandidate.evidence))
                .where(NodeCandidate.id.in_(parent_candidate_ids))
                .order_by(NodeCandidate.id)
                .with_for_update()
            )
            .scalars()
            .unique()
        ) if parent_candidate_ids else []
        parent_candidate_by_id = {
            candidate.id: candidate for candidate in parent_candidates
        }
        project_id = next(iter(projects))
        pending_ids = {candidate.id for candidate in pending}
        for candidate in pending:
            effective = effective_by_id[candidate.id]
            parent_id = effective["parent_candidate_id"]
            if parent_id is None:
                continue
            parent = parent_candidate_by_id.get(parent_id)
            if parent is None:
                raise CandidateValidationError("parent candidate does not exist")
            if parent.id == candidate.id:
                raise CandidateValidationError("candidate cannot be its own parent")
            if parent.project_id != project_id:
                raise CandidateValidationError(
                    "parent candidate belongs to another project"
                )
            parent_effective = (
                effective_by_id[parent.id]
                if parent.id in effective_by_id
                else _effective(parent)
            )
            if parent.review_status == "REJECTED":
                raise CandidateValidationError("REJECTED parent candidate is invalid")
            if parent_effective["disposition"] == "MINUTES_ONLY":
                raise CandidateValidationError(
                    "MINUTES_ONLY parent candidate is invalid"
                )
            if parent.review_status == "PENDING" and parent.id not in pending_ids:
                raise CandidateValidationError(
                    "pending parent candidate must be approved in the same batch"
                )
            if (
                parent.review_status == "APPROVED"
                and parent.confirmed_node_id is None
            ):
                raise CandidateValidationError(
                    "approved parent candidate has no confirmed node"
                )
            if not _parent_type_allowed(
                effective["type"], parent_effective["type"]
            ):
                raise CandidateValidationError(
                    f"{effective['type']} cannot attach to {parent_effective['type']}"
                )

        parent_node_ids = {
            effective["parent_node_id"]
            for effective in effective_by_id.values()
            if effective["parent_node_id"] is not None
        }
        parent_nodes = list(
            session.execute(
                select(Node).where(Node.id.in_(parent_node_ids)).with_for_update()
            ).scalars()
        ) if parent_node_ids else []
        parent_node_by_id = {node.id: node for node in parent_nodes}
        for candidate in pending:
            effective = effective_by_id[candidate.id]
            parent_id = effective["parent_node_id"]
            if parent_id is None:
                continue
            parent = parent_node_by_id.get(parent_id)
            if parent is None:
                raise CandidateValidationError("parent node does not exist")
            if parent.project_id != project_id:
                raise CandidateValidationError(
                    "parent node belongs to another project"
                )
            if parent.graph_state != GraphState.ACTIVE.value:
                raise CandidateValidationError(
                    "parent node must be a confirmed ACTIVE node"
                )
            if not _parent_type_allowed(effective["type"], parent.node_type):
                raise CandidateValidationError(
                    f"{effective['type']} cannot attach to {parent.node_type}"
                )

        created_node_ids: list[str] = []
        created_relation_ids: list[str] = []
        candidate_node: dict[uuid.UUID, Node] = {}
        affected_requests: set[uuid.UUID] = set()

        for candidate in ordered:
            effective = effective_by_id[candidate.id]
            before = _audit_snapshot(candidate)
            disposition = effective["disposition"]
            approved_at = datetime.now(timezone.utc)
            node: Node | None = None
            if disposition != "MINUTES_ONLY":
                category = effective["category"]
                category_row = session.get(Category, category) if category else None
                if category_row is None or not category_row.is_active:
                    raise CandidateValidationError(
                        f"candidate {candidate.id} has no active category"
                    )

                parent_node: Node | None = None
                if disposition == "ATTACH":
                    if effective["parent_candidate_id"] is not None:
                        parent_candidate = parent_candidate_by_id[
                            effective["parent_candidate_id"]
                        ]
                        parent_node = (
                            candidate_node.get(parent_candidate.id)
                            or session.get(Node, parent_candidate.confirmed_node_id)
                        )
                    else:
                        parent_node = parent_node_by_id[
                            effective["parent_node_id"]
                        ]
                    if parent_node is None:
                        raise CandidateValidationError(
                            "effective parent has no confirmed node"
                        )

                node = Node(
                    source_candidate_id=candidate.id,
                    project_id=candidate.project_id,
                    source_meeting_id=candidate.external_meeting_id,
                    source_item_id=candidate.source_item_id,
                    node_type=effective["type"],
                    category=category,
                    title=effective["title"],
                    content=effective["content"],
                    parent_id=parent_node.id if parent_node else None,
                    graph_state=(
                        GraphState.UNATTACHED.value
                        if disposition == "UNATTACHED"
                        else GraphState.ACTIVE.value
                    ),
                    analysis_status="PENDING",
                    lifecycle_status=default_lifecycle_status(effective["type"]),
                    initial_reviewed_by=actor_id,
                    initial_reviewed_at=approved_at,
                    confirmed_by=(
                        actor_id
                        if disposition != "UNATTACHED"
                        else None
                    ),
                    confirmed_at=(
                        approved_at
                        if disposition != "UNATTACHED"
                        else None
                    ),
                )
                session.add(node)
                session.flush()
                candidate_node[candidate.id] = node
                created_node_ids.append(str(node.id))
                for evidence in candidate.evidence:
                    upsert_node_evidence(
                        session,
                        node_id=node.id,
                        segment_id=evidence.segment_id,
                        quote=evidence.quote,
                        quote_start=evidence.quote_start,
                        quote_end=evidence.quote_end,
                        evidence_type=evidence.evidence_type,
                        source_meeting_id=evidence.source_meeting_id,
                    )
                request = session.get(Request, candidate.request_id)
                session.add(
                    GraphChangeEvent(
                        project_id=candidate.project_id,
                        request_id=(
                            request.external_request_id if request is not None else None
                        ),
                        node_id=node.id,
                        item_id=candidate.source_item_id,
                        change_type="CREATE",
                        actor_type="USER",
                        before=None,
                        after=_node_snapshot(node),
                    )
                )

                if disposition == "ATTACH":
                    assert parent_node is not None
                    relation = Relation(
                        project_id=candidate.project_id,
                        from_node_id=node.id,
                        to_node_id=parent_node.id,
                        relation_type="ATTACHED_TO",
                        status="CONFIRMED",
                        actor_type="USER",
                    )
                    session.add(relation)
                    session.flush()
                    created_relation_ids.append(str(relation.id))
                    session.add(
                        GraphChangeEvent(
                            project_id=candidate.project_id,
                            request_id=(
                                request.external_request_id
                                if request is not None
                                else None
                            ),
                            node_id=node.id,
                            item_id=candidate.source_item_id,
                            change_type="ATTACH",
                            actor_type="USER",
                            before=None,
                            after={
                                "relationId": str(relation.id),
                                "fromNodeId": str(node.id),
                                "toNodeId": str(parent_node.id),
                                "relationType": "ATTACHED_TO",
                                "status": "CONFIRMED",
                            },
                        )
                    )

            candidate.review_status = "APPROVED"
            candidate.confirmed_node_id = node.id if node is not None else None
            candidate.initial_review_node_id = (
                node.id if node is not None else None
            )
            candidate.version += 1
            candidate.reviewed_by = actor_id
            candidate.reviewed_at = approved_at
            affected_requests.add(candidate.request_id)
            _add_audit(
                session,
                candidate,
                actor_id=actor_id,
                action="APPROVE",
                before=before,
            )

        _update_review_statuses(session, affected_requests)
        session.commit()
        return CandidateReviewResult(
            candidates=[_candidate_view(candidate) for candidate in ordered_input],
            created_node_ids=created_node_ids,
            created_relation_ids=created_relation_ids,
        )
    except IntegrityError as exc:
        session.rollback()
        with session_factory() as retry_session:
            reloaded = list(
                retry_session.execute(
                    select(NodeCandidate)
                    .options(selectinload(NodeCandidate.evidence))
                    .where(NodeCandidate.id.in_(parsed_ids))
                )
                .scalars()
                .unique()
            )
            if len(reloaded) == len(parsed_ids) and all(
                candidate.review_status == "APPROVED" for candidate in reloaded
            ):
                reloaded_by_id = {candidate.id: candidate for candidate in reloaded}
                return CandidateReviewResult(
                    candidates=[
                        _candidate_view(reloaded_by_id[candidate_id])
                        for candidate_id in parsed_ids
                    ]
                )
        raise CandidateReviewError("approval integrity conflict") from exc
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def approve_candidate(
    session_factory,
    candidate_id: str | uuid.UUID,
    *,
    actor_id: str,
    expected_version: int | None = None,
) -> CandidateReviewResult:
    """Legacy single-candidate wrapper; do not use for the new review flow."""

    expected_versions = (
        {str(candidate_id): expected_version}
        if expected_version is not None
        else None
    )
    return bulk_approve_candidates(
        session_factory,
        [candidate_id],
        actor_id=actor_id,
        expected_versions=expected_versions,
    )


__all__ = [
    "list_candidates",
    "get_candidate",
    "edit_candidate",
    "reject_candidate",
    "complete_initial_review",
    "approve_candidate",
    "bulk_approve_candidates",
]
