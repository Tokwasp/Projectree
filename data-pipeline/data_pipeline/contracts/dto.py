"""스프링 대면 DTO · 이벤트 스키마 자리 (outbox payload).

토폴로지 A: 스프링(Backend/)은 그래프 PG 에 직접 접근하지 않고, 파이프라인이 발행하는
범용 outbox_event 를 통해 반영 결과를 받는다 (연동 자체는 M4). 여기서는 계약 자리만 고정.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .enums import GraphState, NodeType


# --- 스프링이 읽는 노드 투영 DTO ---------------------------------------------
class SpringNodeRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodeId: str
    projectId: str
    nodeType: NodeType
    category: str
    title: str
    content: str
    parentId: str | None
    graphState: GraphState
    lifecycleStatus: str
    version: int
    sourceMeetingId: str
    sourceItemId: str


# --- 그래프 변경 이벤트 (append-only, before/after) --------------------------
class GraphChangeType(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    ATTACH = "ATTACH"
    EXCLUDE = "EXCLUDE"
    DEMOTE = "DEMOTE"      # 서버 검증 실패로 MINUTES_ONLY 강등
    MINUTES_ONLY = "MINUTES_ONLY"


class ActorType(str, Enum):
    AI = "AI"
    USER = "USER"
    SYSTEM = "SYSTEM"


class GraphChangeEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    changeType: GraphChangeType
    nodeId: str | None = None
    itemId: str | None = None
    actorType: ActorType = ActorType.AI
    before: dict | None = None
    after: dict | None = None
    detail: dict = Field(default_factory=dict)


# --- 범용 outbox 이벤트 (전용 outbox·command 테이블 금지) --------------------
class OutboxEventType(str, Enum):
    # v2.2 §5: 범용 outbox 1개 테이블의 이벤트 타입 3종.
    EMBEDDING_REQUESTED = "EMBEDDING_REQUESTED"
    MEETING_PROCESSING_COMPLETED = "MEETING_PROCESSING_COMPLETED"
    GRAPH_CHANGED = "GRAPH_CHANGED"


class OutboxEventPayload(BaseModel):
    """outbox_event.payload(JSONB)에 담기는 범용 이벤트 본문."""

    model_config = ConfigDict(extra="forbid")
    eventType: OutboxEventType
    aggregateType: str            # 예: "meeting_request", "node"
    aggregateId: str
    projectId: str
    schemaVersion: str = "v2.2"
    payload: dict = Field(default_factory=dict)


# --- 반영 결과 (IF-6 요약) ---------------------------------------------------
class CreatedNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    itemId: str
    nodeId: str
    nodeType: NodeType
    parentId: str | None = None


class UpdatedNode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    itemId: str
    nodeId: str
    changes: dict[str, str]
    fromVersion: int
    toVersion: int


class MinutesOnlyEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    itemId: str
    reason: str


class DemotedEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    itemId: str
    fromResult: str | None = None
    rule: str


class ApplyResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requestId: str
    externalMeetingId: str
    status: str  # COMPLETED / STALE / REJECTED / DUPLICATE
    createdNodes: list[CreatedNode] = Field(default_factory=list)
    updatedNodes: list[UpdatedNode] = Field(default_factory=list)
    minutesOnly: list[MinutesOnlyEntry] = Field(default_factory=list)
    demoted: list[DemotedEntry] = Field(default_factory=list)
    detail: dict = Field(default_factory=dict)


class ProposalPersistResult(BaseModel):
    """Generation 결과를 사용자 검토 대기 후보로 저장한 결과."""

    model_config = ConfigDict(extra="forbid")
    requestId: str
    externalMeetingId: str
    status: str  # PROCESSING / REVIEW_PENDING / FAILED
    outcome: str
    candidateIds: list[str] = Field(default_factory=list)
    candidateCount: int = 0
    suggestedDispositionCounts: dict[str, int] = Field(default_factory=dict)
    filled: list[str] = Field(default_factory=list)
    dropped: list[dict] = Field(default_factory=list)
    demoted: list[dict] = Field(default_factory=list)
    invalidEvidence: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    detail: dict = Field(default_factory=dict)


class CandidateEvidenceView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    segment_id: str
    quote: str
    quote_start: int | None = None
    quote_end: int | None = None
    evidence_type: str | None = None
    source_meeting_id: str | None = None


class CandidateView(BaseModel):
    """Review projection including suggested, reviewed, and effective values."""

    model_config = ConfigDict(extra="forbid")
    candidate_id: str
    request_id: str
    source_item_id: str
    project_id: str
    external_meeting_id: str

    suggested_type: str
    suggested_category: str | None = None
    suggested_title: str
    suggested_content: str
    suggested_disposition: str
    suggested_reason: str | None = None
    suggested_parent_candidate_id: str | None = None
    suggested_parent_node_id: str | None = None

    reviewed_type: str | None = None
    reviewed_category: str | None = None
    reviewed_title: str | None = None
    reviewed_content: str | None = None
    reviewed_disposition: str | None = None
    reviewed_parent_mode: str
    reviewed_parent_candidate_id: str | None = None
    reviewed_parent_node_id: str | None = None

    effective_type: str
    effective_category: str | None = None
    effective_title: str
    effective_content: str
    effective_disposition: str
    effective_parent_candidate_id: str | None = None
    effective_parent_node_id: str | None = None

    review_status: str
    version: int
    confirmed_node_id: str | None = None
    evidence: list[CandidateEvidenceView] = Field(default_factory=list)
    created_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by: str | None = None


class CandidateReviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[CandidateView] = Field(default_factory=list)
    created_node_ids: list[str] = Field(default_factory=list)
    created_relation_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
