"""Evaluation-only contracts; no product mutation commands are represented."""

from __future__ import annotations

import uuid
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LabelStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    DISPUTED = "DISPUTED"
    WEAK_LABEL = "WEAK_LABEL"
    UNREVIEWED = "UNREVIEWED"


class EvaluationCase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    case_id: str = Field(alias="caseId")
    project_id: str = Field(alias="projectId")
    source_node_id: uuid.UUID = Field(alias="sourceNodeId")
    source_node_type: str | None = Field(default=None, alias="sourceNodeType")
    expected_action: str | None = Field(default=None, alias="expectedAction")
    expected_target_node_id: uuid.UUID | None = Field(
        default=None,
        alias="expectedTargetNodeId",
    )
    expected_parent_node_id: uuid.UUID | None = Field(
        default=None,
        alias="expectedParentNodeId",
    )
    category: str | None = None
    label_status: LabelStatus = Field(
        default=LabelStatus.UNREVIEWED,
        alias="labelStatus",
    )
    notes: str | None = None


class RetrievedCandidate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    node_id: uuid.UUID = Field(alias="nodeId")
    rank: int
    similarity: float
    node_type: str = Field(alias="nodeType")
    type_valid: bool = Field(alias="typeValid")


class PilotResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    case_id: str = Field(alias="caseId")
    project_id: str = Field(alias="projectId")
    source_node_id: uuid.UUID = Field(alias="sourceNodeId")
    source_node_type: str | None = Field(default=None, alias="sourceNodeType")
    status: str
    reason: str
    candidates: list[RetrievedCandidate] = Field(default_factory=list)
    retrieval_latency_ms: int = Field(default=0, alias="retrievalLatencyMs")
    b_model_action: str | None = Field(default=None, alias="bModelAction")
    b_model_target_node_id: uuid.UUID | None = Field(
        default=None,
        alias="bModelTargetNodeId",
    )
    b_model_confidence: float | None = Field(
        default=None,
        alias="bModelConfidence",
    )


__all__ = [
    "EvaluationCase",
    "LabelStatus",
    "PilotResult",
    "RetrievedCandidate",
]
