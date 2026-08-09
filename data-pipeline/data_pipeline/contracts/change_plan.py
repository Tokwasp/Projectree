"""Change Plan — 검증된 판정을 그래프 반영 명령의 원자 단위로 변환한 것.

Plan 단위 원자 적용: 명령 중 하나라도 실패하면 전체 롤백 (부분 성공 없음).
명령 순서는 planner 가 순차 적용 규칙(evidence 최초 startMs → segmentId → itemId)으로 정렬해
둔다. apply 엔진은 리스트 순서대로 적용한다.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import GraphState, NodeType
from .lineage import Lineage


class PlanOp(str, Enum):
    CREATE_DECISION = "CREATE_DECISION"
    CREATE_ACTION = "CREATE_ACTION"
    CREATE_ISSUE = "CREATE_ISSUE"
    UPDATE_ACTION = "UPDATE_ACTION"
    RECORD_MINUTES = "RECORD_MINUTES"  # 그래프 노드 생성 없음 — 회의록에만 기록(무효/미앵커 항목)


CREATE_OPS = frozenset(
    {PlanOp.CREATE_DECISION.value, PlanOp.CREATE_ACTION.value, PlanOp.CREATE_ISSUE.value}
)


class ParentRef(BaseModel):
    """부모 지정. 셋 다 없으면 root(Decision). 아래 둘 중 하나만 설정 가능."""

    model_config = ConfigDict(extra="forbid")
    newParentItemId: str | None = None   # 이번 회의의 다른 itemId (같은 Plan 내 생성 노드)
    existingNodeId: str | None = None     # 기존 DB 노드 id (후보 목록에서 온 것)

    @model_validator(mode="after")
    def _exactly_one_or_none(self) -> "ParentRef":
        if self.newParentItemId and self.existingNodeId:
            raise ValueError("ParentRef 는 newParentItemId 와 existingNodeId 를 동시에 가질 수 없다")
        return self

    def is_root(self) -> bool:
        return not self.newParentItemId and not self.existingNodeId


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    segmentId: str
    quote: str
    quoteStart: int | None = None  # 서버 역산 char 오프셋 (규칙 4)
    quoteEnd: int | None = None


class SortKey(BaseModel):
    """순차 적용 정렬 키. LLM 배열 순서 대신 evidence 시각 기준."""

    model_config = ConfigDict(extra="forbid")
    startMs: int = Field(default=2_147_483_647)  # 없으면 맨 뒤
    segmentId: str = ""
    itemId: str = ""

    def as_tuple(self) -> tuple[int, str, str]:
        return (self.startMs, self.segmentId, self.itemId)


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")

    op: PlanOp
    itemId: str
    sortKey: SortKey

    # create 계열
    nodeType: NodeType | None = None
    category: str | None = None
    title: str | None = None
    content: str | None = None
    parent: ParentRef | None = None
    graphState: GraphState = GraphState.ACTIVE  # UNATTACHED 판정은 UNATTACHED 노드로 보존
    evidence: list[EvidenceRef] = Field(default_factory=list)

    # update 계열
    targetActionId: str | None = None
    changes: dict[str, str] | None = None
    expectedVersion: int | None = None  # optimistic lock

    # record minutes
    reason: str | None = None

    @model_validator(mode="after")
    def _shape_by_op(self) -> "Command":
        op = self.op
        if op.value in CREATE_OPS:
            if self.nodeType is None or not self.title:
                raise ValueError(f"{op.value} 는 nodeType 과 title 이 필요하다")
            if not self.evidence:
                raise ValueError(f"{op.value} 는 evidence 가 1개 이상 필요하다")
        elif op == PlanOp.UPDATE_ACTION:
            if not self.targetActionId or not self.changes:
                raise ValueError("UPDATE_ACTION 은 targetActionId 와 changes 가 필요하다")
        elif op == PlanOp.RECORD_MINUTES:
            if not self.reason:
                raise ValueError("RECORD_MINUTES 는 reason 이 필요하다")
        return self


class ChangePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planId: str
    projectId: str
    externalMeetingId: str
    requestId: str
    lineage: Lineage
    commands: list[Command] = Field(default_factory=list)

    def sorted_commands(self) -> list[Command]:
        """순차 적용 순서 (정렬 키 기준). planner 가 이미 정렬해 두지만 방어적으로 재정렬."""
        return sorted(self.commands, key=lambda c: c.sortKey.as_tuple())
