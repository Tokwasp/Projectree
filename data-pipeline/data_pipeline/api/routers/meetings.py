"""Meeting-level pipeline status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from data_pipeline.api.dependencies import get_project_id, get_session_factory
from data_pipeline.api.schemas import (
    Identifier,
    MeetingSummaryView,
    PipelineStatusResponse,
)
from data_pipeline.api.services import build_pipeline_status
from data_pipeline.meeting_summary import get_meeting_summary

router = APIRouter(prefix="/api/v1", tags=["meetings"])


@router.get(
    "/meetings/{meeting_id}/pipeline-status",
    response_model=PipelineStatusResponse,
)
def pipeline_status(
    meeting_id: Identifier,
    project_id: str = Depends(get_project_id),
    session_factory=Depends(get_session_factory),
) -> PipelineStatusResponse:
    return build_pipeline_status(
        session_factory, project_id=project_id, meeting_id=meeting_id
    )


@router.get(
    "/meetings/{meeting_id}/summary",
    response_model=MeetingSummaryView,
)
def meeting_summary(
    meeting_id: Identifier,
    summary_version: int | None = Query(
        default=None,
        alias="summaryVersion",
        ge=1,
    ),
    project_id: str = Depends(get_project_id),
    session_factory=Depends(get_session_factory),
) -> MeetingSummaryView:
    result = get_meeting_summary(
        session_factory,
        project_id=project_id,
        external_meeting_id=meeting_id,
        summary_version=summary_version,
    )
    structured = result.structured_summary
    return MeetingSummaryView(
        meetingSummaryId=str(result.summary_id),
        projectId=result.project_id,
        externalMeetingId=result.external_meeting_id,
        summaryVersion=result.summary_version,
        status="READY",
        title=result.title,
        body=result.body,
        decisions=list(structured.get("decisions", [])),
        actions=list(structured.get("actions", [])),
        issues=list(structured.get("issues", [])),
        generatorName=result.generator_name,
        generatorVersion=result.generator_version,
        createdAt=result.created_at,
    )


__all__ = ["router"]
