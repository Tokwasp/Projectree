"""Request and response models for the review API.

Request DTOs are separate from response DTOs, and ORM objects are never
returned directly: responses are built from the pipeline's own contract models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_pipeline.contracts import CandidateView

NodeTypeLiteral = Literal["DECISION", "ACTION", "ISSUE", "UNKNOWN"]
DispositionLiteral = Literal["UNATTACHED", "MINUTES_ONLY", "ATTACH"]
ActionLifecycleLiteral = Literal["TODO", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
ParentModeLiteral = Literal["INHERIT", "CANDIDATE", "NODE", "NONE"]
Identifier = Annotated[str, Field(min_length=1, max_length=128)]

MAX_TITLE_LENGTH = 300
MAX_CONTENT_LENGTH = 20_000
MAX_CANDIDATES_PER_REQUEST = 200


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "degraded"]
    checks: dict[str, str] = Field(default_factory=dict)


class CandidateListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meetingId: str
    total: int
    candidates: list[CandidateView]


class CandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidate: CandidateView


class CandidateReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[CandidateView]
    createdNodeIds: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CandidatePatchRequest(BaseModel):
    """Only supplied fields are changed; omitted fields are left untouched."""

    model_config = ConfigDict(extra="forbid")
    expectedVersion: int = Field(..., ge=1)
    nodeType: NodeTypeLiteral | None = None
    category: str | None = Field(default=None, min_length=1, max_length=64)
    title: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_TITLE_LENGTH,
    )
    content: str | None = Field(default=None, max_length=MAX_CONTENT_LENGTH)
    disposition: DispositionLiteral | None = None
    #: Explicit null clears the reviewer override and falls back to the suggestion.
    lifecycleStatus: ActionLifecycleLiteral | None = None
    parentMode: ParentModeLiteral | None = None
    parentCandidateId: Identifier | None = None
    parentNodeId: Identifier | None = None


class VersionedActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectedVersion: int | None = Field(default=None, ge=1)


class InitialReviewCompleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: When empty, every PENDING candidate of the meeting is completed.
    candidateIds: list[Identifier] = Field(
        default_factory=list,
        max_length=MAX_CANDIDATES_PER_REQUEST,
    )

    @field_validator("candidateIds")
    @classmethod
    def candidate_ids_must_be_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("candidateIds must not contain duplicates")
        return value


class InitialReviewCompleteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meetingId: str
    status: Literal["ANALYSIS_PENDING"]
    reviewedCandidateCount: int
    createdNodeCount: int
    queuedAnalysisJobCount: int
    createdNodeIds: list[str] = Field(default_factory=list)


class PipelineStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meetingId: str
    projectId: str
    meetingStatus: str | None = None
    requestStatus: str | None = None
    candidateCounts: dict[str, int] = Field(default_factory=dict)
    nodeCounts: dict[str, int] = Field(default_factory=dict)
    analysisJobCounts: dict[str, int] = Field(default_factory=dict)
    pipelineStage: str


class AnalysisJobView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    jobId: str
    nodeId: str
    status: str
    attemptCount: int
    maxAttempts: int
    failureCode: str | None = None
    availableAt: datetime
    updatedAt: datetime


class AnalysisStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meetingId: str
    status: str
    jobs: list[AnalysisJobView] = Field(default_factory=list)


class AnalysisCandidateView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysisCandidateId: str
    projectId: str
    analysisRunId: str
    sourceNodeId: str
    sourceNodeVersion: int
    targetNodeId: str | None = None
    targetNodeVersion: int | None = None
    recommendation: str
    relationType: str | None = None
    suggestedTitle: str
    suggestedContent: str
    reason: str
    status: str
    version: int
    createdAt: datetime


class FinalReviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meetingId: str
    total: int
    analysisCandidates: list[AnalysisCandidateView]


class AnalysisDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectedVersion: int = Field(..., ge=1)


class MergeApprovalRequest(AnalysisDecisionRequest):
    model_config = ConfigDict(extra="forbid")
    confirmUnattachedTarget: bool = False
    mergedTitle: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_TITLE_LENGTH,
    )
    mergedContent: str | None = Field(
        default=None,
        max_length=MAX_CONTENT_LENGTH,
    )


class AnalysisDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysisCandidateId: str
    status: str
    sourceNodeId: str
    targetNodeId: str | None = None
    relationId: str | None = None
    mergeHistoryId: str | None = None


class ReanalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectedVersion: int = Field(..., ge=1)


class ReanalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodeId: str
    status: Literal["ANALYSIS_PENDING"]
    analysisRunId: str
    created: bool
    queuedAnalysisJobCount: int


__all__ = [
    "AnalysisCandidateView",
    "AnalysisDecisionRequest",
    "AnalysisDecisionResponse",
    "AnalysisJobView",
    "AnalysisStatusResponse",
    "CandidateListResponse",
    "CandidatePatchRequest",
    "CandidateResponse",
    "CandidateReviewResponse",
    "FinalReviewResponse",
    "HealthResponse",
    "InitialReviewCompleteRequest",
    "InitialReviewCompleteResponse",
    "MergeApprovalRequest",
    "PipelineStatusResponse",
    "ReanalyzeRequest",
    "ReanalyzeResponse",
    "VersionedActionRequest",
]
