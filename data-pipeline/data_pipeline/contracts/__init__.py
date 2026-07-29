"""v2.2 계약 (pydantic). node/graph_state/lifecycle 분리, 부모 규칙, 관계, 설정 기반 카테고리,
Change Plan, 스프링 DTO·이벤트, lineage."""

from __future__ import annotations

from .category import CategorySet
from .change_plan import (
    CREATE_OPS,
    ChangePlan,
    Command,
    EvidenceRef,
    ParentRef,
    PlanOp,
    SortKey,
)
from .dto import (
    ActorType,
    ApplyResult,
    CandidateEvidenceView,
    CandidateReviewResult,
    CandidateView,
    CreatedNode,
    DemotedEntry,
    GraphChangeEventPayload,
    GraphChangeType,
    MinutesOnlyEntry,
    OutboxEventPayload,
    OutboxEventType,
    ProposalPersistResult,
    SpringNodeRow,
    UpdatedNode,
)
from .enums import (
    ALLOWED_RESULTS_BY_TYPE,
    CHANGES_ALLOWED_KEYS,
    GRAPH_RESULTS,
    LIFECYCLE_STATUSES_BY_TYPE,
    LIFECYCLE_TRANSITIONS,
    TERMINAL_STATUSES,
    ActionStatus,
    DecisionStatus,
    GraphState,
    IssueStatus,
    JudgmentResult,
    MinutesReason,
    NodeType,
    RelationStatus,
    RelationType,
    default_lifecycle_status,
    lifecycle_status_valid,
    parent_rule_violation,
    result_allowed_for_type,
    transition_allowed,
)
from .io import (
    CandidateAction,
    CandidateDecision,
    Candidates,
    Evidence,
    ExtractedItem,
    ExtractionOutput,
    Judgment,
    JudgmentOutput,
    MeetingTranscript,
    Segment,
)
from .lineage import PIPELINE_VERSION, SCHEMA_VERSION, Lineage

__all__ = [
    "CategorySet",
    "ChangePlan", "Command", "ParentRef", "PlanOp", "SortKey", "EvidenceRef", "CREATE_OPS",
    "ApplyResult", "CreatedNode", "UpdatedNode", "MinutesOnlyEntry", "DemotedEntry",
    "CandidateEvidenceView", "CandidateView", "CandidateReviewResult",
    "ProposalPersistResult",
    "SpringNodeRow", "GraphChangeEventPayload", "GraphChangeType", "ActorType",
    "OutboxEventPayload", "OutboxEventType",
    "NodeType", "GraphState", "DecisionStatus", "ActionStatus", "IssueStatus",
    "RelationType", "RelationStatus", "JudgmentResult", "MinutesReason",
    "LIFECYCLE_STATUSES_BY_TYPE", "LIFECYCLE_TRANSITIONS", "TERMINAL_STATUSES",
    "ALLOWED_RESULTS_BY_TYPE", "CHANGES_ALLOWED_KEYS", "GRAPH_RESULTS",
    "default_lifecycle_status", "lifecycle_status_valid", "transition_allowed",
    "result_allowed_for_type", "parent_rule_violation",
    "Segment", "MeetingTranscript", "Evidence", "ExtractedItem", "ExtractionOutput",
    "CandidateAction", "CandidateDecision", "Candidates",
    "Judgment", "JudgmentOutput",
    "Lineage", "PIPELINE_VERSION", "SCHEMA_VERSION",
]
