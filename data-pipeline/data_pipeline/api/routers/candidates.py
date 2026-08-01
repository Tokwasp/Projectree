"""Candidate listing, editing and initial review."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from data_pipeline.api.dependencies import (
    get_actor_id,
    get_project_id,
    get_session_factory,
)
from data_pipeline.api.schemas import (
    CandidateListResponse,
    CandidatePatchRequest,
    CandidateResponse,
    CandidateReviewResponse,
    Identifier,
    InitialReviewCompleteRequest,
    InitialReviewCompleteResponse,
    VersionedActionRequest,
)
from data_pipeline.api.services import complete_meeting_initial_review
from data_pipeline.pipeline import (
    UNSET,
    complete_initial_review,
    edit_candidate,
    get_candidate,
    list_candidates,
    reject_candidate,
)

router = APIRouter(prefix="/api/v1", tags=["candidates"])


@router.get(
    "/meetings/{meeting_id}/candidates",
    response_model=CandidateListResponse,
)
def list_meeting_candidates(
    meeting_id: Identifier,
    review_status: str | None = Query(
        default=None,
        alias="reviewStatus",
        max_length=16,
    ),
    node_type: str | None = Query(
        default=None,
        alias="nodeType",
        max_length=16,
    ),
    project_id: str = Depends(get_project_id),
    session_factory=Depends(get_session_factory),
) -> CandidateListResponse:
    candidates = list_candidates(
        session_factory,
        project_id=project_id,
        external_meeting_id=meeting_id,
        review_status=review_status,
        node_type=node_type,
    )
    return CandidateListResponse(
        meetingId=meeting_id,
        total=len(candidates),
        candidates=candidates,
    )


@router.get("/candidates/{candidate_id}", response_model=CandidateResponse)
def read_candidate(
    candidate_id: Identifier,
    project_id: str = Depends(get_project_id),
    session_factory=Depends(get_session_factory),
) -> CandidateResponse:
    return CandidateResponse(
        candidate=get_candidate(
            session_factory, candidate_id, project_id=project_id
        )
    )


@router.patch("/candidates/{candidate_id}", response_model=CandidateReviewResponse)
def patch_candidate(
    candidate_id: Identifier,
    payload: CandidatePatchRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> CandidateReviewResponse:
    supplied = payload.model_fields_set
    result = edit_candidate(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=payload.expectedVersion,
        node_type=payload.nodeType if "nodeType" in supplied else UNSET,
        category=payload.category if "category" in supplied else UNSET,
        title=payload.title if "title" in supplied else UNSET,
        content=payload.content if "content" in supplied else UNSET,
        disposition=payload.disposition if "disposition" in supplied else UNSET,
        lifecycle_status=(
            payload.lifecycleStatus if "lifecycleStatus" in supplied else UNSET
        ),
        parent_mode=payload.parentMode,
        parent_candidate_id=payload.parentCandidateId,
        parent_node_id=payload.parentNodeId,
    )
    return CandidateReviewResponse(
        candidates=result.candidates,
        createdNodeIds=result.created_node_ids,
        warnings=result.warnings,
    )


@router.post(
    "/candidates/{candidate_id}/approve",
    response_model=CandidateReviewResponse,
)
def approve_candidate_endpoint(
    candidate_id: Identifier,
    payload: VersionedActionRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> CandidateReviewResponse:
    """Approve one candidate, materializing it as an UNATTACHED Node.

    Analysis is NOT started here; use the meeting-level initial-review/complete
    endpoint to enqueue analysis once the reviewer is finished.
    """

    result = complete_initial_review(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=payload.expectedVersion,
    )
    return CandidateReviewResponse(
        candidates=result.candidates,
        createdNodeIds=result.created_node_ids,
        warnings=result.warnings,
    )


@router.post(
    "/candidates/{candidate_id}/reject",
    response_model=CandidateReviewResponse,
)
def reject_candidate_endpoint(
    candidate_id: Identifier,
    payload: VersionedActionRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> CandidateReviewResponse:
    result = reject_candidate(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=payload.expectedVersion,
    )
    return CandidateReviewResponse(
        candidates=result.candidates,
        createdNodeIds=result.created_node_ids,
        warnings=result.warnings,
    )


@router.post(
    "/meetings/{meeting_id}/initial-review/complete",
    response_model=InitialReviewCompleteResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def complete_initial_review_endpoint(
    meeting_id: Identifier,
    payload: InitialReviewCompleteRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> InitialReviewCompleteResponse:
    """Finish initial review and hand analysis to the worker.

    Returns 202: embedding, Retrieval and the B model run out of band so the
    request never blocks on an external provider.
    """

    return complete_meeting_initial_review(
        session_factory,
        project_id=project_id,
        meeting_id=meeting_id,
        actor_id=actor_id,
        candidate_ids=payload.candidateIds,
    )


__all__ = ["router"]
