"""LLM ①·② 입출력 계약 (IF-1 ~ IF-4). PoC v3 스키마의 규칙을 v2.2 계약으로 재작성.

카테고리는 설정 기반이므로 여기서는 str 로 두고, 유효성은 validation 레이어에서 CategorySet
으로 검증한다 (하드코딩 enum 금지). type/판정만 enum 으로 고정한다.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import JudgmentResult, MinutesReason, NodeType


# --- IF-1: STT 세그먼트 -------------------------------------------------------
class Segment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    segmentId: str
    text: str
    rawText: str | None = None
    normalizedText: str | None = None
    normalization: dict | None = None
    startMs: int | None = None
    endMs: int | None = None
    speakerLabel: str | None = None


class MeetingTranscript(BaseModel):
    model_config = ConfigDict(extra="ignore")
    meetingId: str
    segments: list[Segment]

    def segment_map(self) -> dict[str, str]:
        return {s.segmentId: s.text for s in self.segments}

    def start_ms_map(self) -> dict[str, int | None]:
        return {s.segmentId: s.startMs for s in self.segments}


# --- IF-2: 추출 항목 (LLM ①) --------------------------------------------------
class Evidence(BaseModel):
    model_config = ConfigDict(extra="ignore")
    segmentId: str
    quote: str


class ExtractedItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    type: NodeType
    predictedCategory: str  # 검색 부스트 전용. validation 에서 CategorySet 검증.
    title: str
    content: str
    evidence: list[Evidence] = Field(min_length=1)
    note: str | None = None
    # ACTION 의 시제 기반 진행 상태. 동결된 LTS 프롬프트는 아직 이 필드를 내지 않으므로
    # 기본값은 None 이고, 그 경우 기존 default_lifecycle_status 로 폴백한다.
    # 새 프롬프트 프로파일이 이 값을 채우면 Candidate → Node 까지 그대로 전달된다.
    lifecycleStatus: str | None = None


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    meetingId: str
    items: list[ExtractedItem]


# --- IF-3: 검색 후보 (③ 출력 = ② 입력의 일부) --------------------------------
class CandidateAction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    actionId: str
    title: str
    status: str = "IN_PROGRESS"


class CandidateDecision(BaseModel):
    model_config = ConfigDict(extra="ignore")
    decisionId: str
    title: str
    content: str | None = None
    category: str | None = None
    status: str = "ACTIVE"
    actions: list[CandidateAction] = Field(default_factory=list)


class Candidates(BaseModel):
    model_config = ConfigDict(extra="ignore")
    decisions: list[CandidateDecision] = Field(default_factory=list)

    def decision_ids(self) -> set[str]:
        return {d.decisionId for d in self.decisions}

    def action_status_map(self) -> dict[str, str]:
        return {a.actionId: a.status for d in self.decisions for a in d.actions}


# --- IF-4: 판정 (LLM ②) ------------------------------------------------------
class Judgment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    itemId: str
    result: JudgmentResult
    category: str | None = None
    attachTo: str | None = None
    reason: MinutesReason | None = None
    targetActionId: str | None = None
    changes: dict[str, str] | None = None
    note: str | None = None


class JudgmentOutput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    meetingId: str
    judgments: list[Judgment]
