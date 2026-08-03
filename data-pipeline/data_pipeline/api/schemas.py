"""Request and response models for the review API.

Request DTOs are separate from response DTOs, and ORM objects are never
returned directly: responses are built from the pipeline's own contract models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data_pipeline.contracts import CandidateView

NodeTypeLiteral = Literal["DECISION", "ACTION", "ISSUE", "UNKNOWN"]
DispositionLiteral = Literal["UNATTACHED", "MINUTES_ONLY", "ATTACH"]
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


class UserNodeDecisionRequest(BaseModel):
    """A user's final graph decision, independent of a B-model recommendation."""

    model_config = ConfigDict(extra="forbid")
    requestedAction: Literal["CREATE_NEW", "LINK", "MERGE"]
    sourceExpectedVersion: int = Field(..., ge=1)
    targetNodeId: Identifier | None = None
    targetExpectedVersion: int | None = Field(default=None, ge=1)
    relationType: Literal["ATTACHED_TO", "RELATED_TO"] | None = None
    analysisRunId: Identifier | None = None
    recommendationId: Identifier | None = None
    mergedTitle: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_TITLE_LENGTH,
    )
    mergedContent: str | None = Field(
        default=None,
        max_length=MAX_CONTENT_LENGTH,
    )

    @model_validator(mode="after")
    def validate_action_shape(self):
        action = self.requestedAction
        if action == "CREATE_NEW":
            if any(
                value is not None
                for value in (
                    self.targetNodeId,
                    self.targetExpectedVersion,
                    self.relationType,
                    self.mergedTitle,
                    self.mergedContent,
                )
            ):
                raise ValueError(
                    "CREATE_NEW does not accept target, relation, or merge fields"
                )
        elif action == "LINK":
            if (
                self.targetNodeId is None
                or self.targetExpectedVersion is None
                or self.relationType is None
            ):
                raise ValueError(
                    "LINK requires targetNodeId, targetExpectedVersion, "
                    "and relationType"
                )
            if (
                self.mergedTitle is not None
                or self.mergedContent is not None
            ):
                raise ValueError("LINK does not accept merge fields")
        else:
            if self.targetNodeId is None or self.targetExpectedVersion is None:
                raise ValueError(
                    "MERGE requires targetNodeId and targetExpectedVersion"
                )
            if self.relationType is not None:
                raise ValueError("MERGE does not accept relationType")
            if self.mergedTitle is None or self.mergedContent is None:
                raise ValueError(
                    "manual MERGE requires mergedTitle and mergedContent"
                )
        return self


class UserNodeDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["APPLIED"]
    requestedAction: Literal["CREATE_NEW", "LINK", "MERGE"]
    sourceNodeId: str
    targetNodeId: str | None = None
    relationId: str | None = None
    mergeHistoryId: str | None = None
    graphChangeEventId: str
    replayed: bool


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


class EvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidenceId: str
    sourceType: str
    meetingId: str | None = None
    segmentId: str | None = None
    speakerLabel: str | None = None
    startMs: int | None = None
    endMs: int | None = None
    quoteStart: int | None = None
    quoteEnd: int | None = None
    quotedText: str


class GraphNodeView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodeId: str
    canonicalNodeId: str
    projectId: str
    nodeType: str
    category: str
    title: str
    content: str
    dueDate: str | None = None
    graphState: str
    consistencyStatus: str
    parentNodeId: str | None = None
    mergedIntoNodeId: str | None = None
    originType: str
    version: int
    evidence: list[EvidenceView] = Field(default_factory=list)


class GraphNodeListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    total: int
    nodes: list[GraphNodeView]


class GraphNodePatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectedVersion: int = Field(..., ge=1)
    title: str | None = Field(
        default=None, min_length=1, max_length=MAX_TITLE_LENGTH
    )
    content: str | None = Field(default=None, max_length=MAX_CONTENT_LENGTH)
    nodeType: Literal["DECISION", "ACTION", "ISSUE"] | None = None
    category: str | None = Field(default=None, min_length=1, max_length=64)
    dueDate: str | None = Field(default=None, max_length=32)
    evidenceAssertion: str | None = Field(default=None, min_length=1, max_length=20_000)
    newParentNodeId: Identifier | None = None


class UserNodeCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodeType: Literal["DECISION", "ACTION", "ISSUE"]
    category: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=MAX_TITLE_LENGTH)
    content: str = Field(default="", max_length=MAX_CONTENT_LENGTH)
    dueDate: str | None = Field(default=None, max_length=32)
    evidenceAssertion: str = Field(..., min_length=1, max_length=20_000)
    externalMeetingId: str | None = Field(default=None, max_length=128)


class NodeDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectedVersion: int = Field(..., ge=1)


class LogicalMergeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    targetNodeId: Identifier
    sourceExpectedVersion: int = Field(..., ge=1)
    targetExpectedVersion: int = Field(..., ge=1)
    reason: str = Field(..., min_length=1, max_length=2_000)


class GraphMutationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodeId: str
    version: int
    graphState: str
    operationId: str | None = None
    relationId: str | None = None
    changed: bool


class RelationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fromNodeId: Identifier
    toNodeId: Identifier
    relationType: Literal[
        "ATTACHED_TO", "RELATED_TO", "SAME", "REVERSES", "FOLLOWS", "RESOLVED_BY"
    ]
    fromExpectedVersion: int = Field(..., ge=1)
    toExpectedVersion: int = Field(..., ge=1)


class RelationReplaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    toNodeId: Identifier
    relationType: Literal[
        "ATTACHED_TO", "RELATED_TO", "SAME", "REVERSES", "FOLLOWS", "RESOLVED_BY"
    ]
    fromExpectedVersion: int = Field(..., ge=1)
    toExpectedVersion: int = Field(..., ge=1)


class RelationView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relationId: str
    fromNodeId: str
    toNodeId: str
    relationType: str
    status: str
    validFrom: datetime
    validTo: datetime | None = None


class GenerationRunView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generationRunId: str
    projectId: str
    externalMeetingId: str
    status: str
    warnings: list[dict] = Field(default_factory=list)
    resultSummary: dict = Field(default_factory=dict)
    failureCode: str | None = None
    failureMessage: str | None = None
    startedAt: datetime | None = None
    completedAt: datetime | None = None


class MeetingSummaryView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meetingSummaryId: str
    projectId: str
    externalMeetingId: str
    summaryVersion: int = Field(..., ge=1)
    status: Literal["READY"]
    title: str
    body: str
    decisions: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    generatorName: str
    generatorVersion: str
    createdAt: datetime


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
    "MeetingSummaryView",
    "PipelineStatusResponse",
    "ReanalyzeRequest",
    "ReanalyzeResponse",
    "UserNodeDecisionRequest",
    "UserNodeDecisionResponse",
    "VersionedActionRequest",
    "EvidenceView",
    "GenerationRunView",
    "GraphMutationResponse",
    "GraphNodeListResponse",
    "GraphNodePatchRequest",
    "GraphNodeView",
    "LogicalMergeRequest",
    "NodeDeleteRequest",
    "RelationCreateRequest",
    "RelationReplaceRequest",
    "RelationView",
    "UserNodeCreateRequest",
]
