"""Meeting-level pipeline status."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from data_pipeline.api.dependencies import get_project_id, get_session_factory
from data_pipeline.api.schemas import Identifier, PipelineStatusResponse
from data_pipeline.api.services import build_pipeline_status

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


__all__ = ["router"]
