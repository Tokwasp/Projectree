"""Analysis status, final review, and final-approval decisions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from data_pipeline.api.dependencies import (
    get_actor_id,
    get_project_id,
    get_session_factory,
)
from data_pipeline.api.schemas import (
    AnalysisDecisionRequest,
    AnalysisDecisionResponse,
    AnalysisStatusResponse,
    FinalReviewResponse,
    Identifier,
    MergeApprovalRequest,
    ReanalyzeRequest,
    ReanalyzeResponse,
)
from data_pipeline.api.services import (
    build_analysis_status,
    build_final_review,
    queue_analysis_for_node,
)
from data_pipeline.pipeline import (
    approve_create_new,
    approve_link_existing,
    approve_merge_existing,
    reanalyze_unattached_node,
    reject_analysis_candidate,
)

router = APIRouter(prefix="/api/v1", tags=["analysis"])


@router.get(
    "/meetings/{meeting_id}/analysis-status",
    response_model=AnalysisStatusResponse,
)
def analysis_status(
    meeting_id: Identifier,
    project_id: str = Depends(get_project_id),
    session_factory=Depends(get_session_factory),
) -> AnalysisStatusResponse:
    return build_analysis_status(
        session_factory, project_id=project_id, meeting_id=meeting_id
    )


@router.get(
    "/meetings/{meeting_id}/final-review",
    response_model=FinalReviewResponse,
)
def final_review(
    meeting_id: Identifier,
    project_id: str = Depends(get_project_id),
    session_factory=Depends(get_session_factory),
) -> FinalReviewResponse:
    return build_final_review(
        session_factory, project_id=project_id, meeting_id=meeting_id
    )


@router.post(
    "/nodes/{node_id}/reanalyze",
    response_model=ReanalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def reanalyze_node(
    node_id: Identifier,
    payload: ReanalyzeRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> ReanalyzeResponse:
    """Register a fresh analysis run and queue it; the worker does the work."""

    requested = reanalyze_unattached_node(
        session_factory,
        node_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=payload.expectedVersion,
    )
    queued = queue_analysis_for_node(
        session_factory, project_id=project_id, node_id=uuid.UUID(str(node_id))
    )
    return ReanalyzeResponse(
        nodeId=str(node_id),
        status="ANALYSIS_PENDING",
        analysisRunId=str(requested.run.analysis_run_id),
        created=requested.created,
        queuedAnalysisJobCount=queued,
    )


def _decision_response(candidate_id: str, result) -> AnalysisDecisionResponse:
    return AnalysisDecisionResponse(
        analysisCandidateId=candidate_id,
        status=result.candidate.status.value,
        sourceNodeId=str(getattr(result, "source_node_id", "")),
        targetNodeId=(
            str(result.target_node_id)
            if getattr(result, "target_node_id", None)
            else None
        ),
        relationId=(
            str(result.relation_id) if getattr(result, "relation_id", None) else None
        ),
        mergeHistoryId=(
            str(result.merge_history_id)
            if getattr(result, "merge_history_id", None)
            else None
        ),
    )


@router.post(
    "/analysis-candidates/{candidate_id}/approve-create",
    response_model=AnalysisDecisionResponse,
)
def approve_create(
    candidate_id: Identifier,
    payload: AnalysisDecisionRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> AnalysisDecisionResponse:
    result = approve_create_new(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=payload.expectedVersion,
    )
    return _decision_response(candidate_id, result)


@router.post(
    "/analysis-candidates/{candidate_id}/approve-link",
    response_model=AnalysisDecisionResponse,
)
def approve_link(
    candidate_id: Identifier,
    payload: AnalysisDecisionRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> AnalysisDecisionResponse:
    result = approve_link_existing(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=payload.expectedVersion,
    )
    return _decision_response(candidate_id, result)


@router.post(
    "/analysis-candidates/{candidate_id}/approve-merge",
    response_model=AnalysisDecisionResponse,
)
def approve_merge(
    candidate_id: Identifier,
    payload: MergeApprovalRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> AnalysisDecisionResponse:
    result = approve_merge_existing(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=payload.expectedVersion,
        confirm_unattached_target=payload.confirmUnattachedTarget,
        merged_title=payload.mergedTitle,
        merged_content=payload.mergedContent,
    )
    return _decision_response(candidate_id, result)


@router.post(
    "/analysis-candidates/{candidate_id}/reject",
    response_model=AnalysisDecisionResponse,
)
def reject_analysis(
    candidate_id: Identifier,
    payload: AnalysisDecisionRequest,
    project_id: str = Depends(get_project_id),
    actor_id: str = Depends(get_actor_id),
    session_factory=Depends(get_session_factory),
) -> AnalysisDecisionResponse:
    result = reject_analysis_candidate(
        session_factory,
        candidate_id,
        project_id=project_id,
        actor_id=actor_id,
        expected_version=payload.expectedVersion,
    )
    return _decision_response(candidate_id, result)


__all__ = ["router"]
