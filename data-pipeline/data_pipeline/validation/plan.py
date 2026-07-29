"""규칙 8(생성) — 검증된 판정 → Change Plan (원자 적용 단위).

판정별 명령 매핑:
  NEW_DECISION  -> CREATE_DECISION (root)
  ATTACH        -> CREATE_ACTION / CREATE_ISSUE (부모 = 같은 회의 itemId 또는 기존 node uuid)
  UPDATE_ACTION -> UPDATE_ACTION (targetActionId=기존 액션 node uuid, changes, expectedVersion)
  MINUTES_ONLY  -> RECORD_MINUTES (그래프 노드 없음)

명령은 순차 적용 정렬 키(evidence 최초 startMs→segmentId→itemId)로 정렬한다.
규칙 7(기술적 중복)의 사전 감지용 시그니처 계산 헬퍼도 여기 둔다.
"""

from __future__ import annotations

from data_pipeline.contracts import (
    CategorySet,
    ChangePlan,
    Command,
    EvidenceRef,
    GraphState,
    Lineage,
    NodeType,
    ParentRef,
    PlanOp,
    SortKey,
)

from .evidence import SegmentInfo, resolve_item_evidence
from .judgments import ValidationResult
from .normalize import normalize_quote

_FALLBACK_CATEGORY = "ETC"

_ATTACH_OP_BY_TYPE = {
    NodeType.ACTION.value: PlanOp.CREATE_ACTION,
    NodeType.ISSUE.value: PlanOp.CREATE_ISSUE,
}
_CREATE_OP_BY_TYPE = {
    NodeType.DECISION.value: PlanOp.CREATE_DECISION,
    NodeType.ACTION.value: PlanOp.CREATE_ACTION,
    NodeType.ISSUE.value: PlanOp.CREATE_ISSUE,
}


def _coerce_category(value: str | None, category_set: CategorySet) -> str:
    if value and category_set.is_valid(value):
        return value
    if category_set.is_valid(_FALLBACK_CATEGORY):
        return _FALLBACK_CATEGORY
    return category_set.values[0]


def _evidence_refs(item: dict, segments: dict[str, SegmentInfo]) -> list[EvidenceRef]:
    """서버 오프셋 역산(규칙 4)을 EvidenceRef 에 실어 apply 가 node_evidence 에 저장하게 한다."""
    res = resolve_item_evidence(item, segments)
    offsets = {(r.segment_id): (r.char_start, r.char_end) for r in res.resolved}
    refs: list[EvidenceRef] = []
    for ev in item.get("evidence") or []:
        sid = ev.get("segmentId")
        if not sid:
            continue
        cstart, cend = offsets.get(sid, (None, None))
        refs.append(EvidenceRef(segmentId=sid, quote=ev.get("quote", ""), quoteStart=cstart, quoteEnd=cend))
    return refs


def _sort_key(item: dict, segments: dict[str, SegmentInfo]) -> SortKey:
    res = resolve_item_evidence(item, segments)
    return SortKey(
        startMs=res.earliest_start_ms if res.earliest_start_ms is not None else 2_147_483_647,
        segmentId=res.earliest_segment_id or "",
        itemId=str(item.get("id")),
    )


def build_change_plan(
    *,
    plan_id: str,
    project_id: str,
    external_meeting_id: str,
    request_id: str,
    items: list[dict],
    validation: ValidationResult,
    segments: dict[str, SegmentInfo],
    lineage: Lineage,
    category_set: CategorySet,
    action_versions: dict[str, int] | None = None,
) -> ChangePlan:
    action_versions = action_versions or {}
    items_by_id = {str(it.get("id")): it for it in items}
    judgment_by_id = {str(j.get("itemId")): j for j in validation.judgments}
    item_ids = set(items_by_id)

    commands: list[Command] = []
    for item_id, item in items_by_id.items():
        judgment = judgment_by_id.get(item_id)
        if judgment is None:
            continue
        result = str(judgment.get("result"))
        ntype = str(item.get("type")).upper()
        sort_key = _sort_key(item, segments)

        if result == "NEW_DECISION":
            commands.append(Command(
                op=PlanOp.CREATE_DECISION,
                itemId=item_id,
                sortKey=sort_key,
                nodeType=NodeType.DECISION,
                category=_coerce_category(judgment.get("category") or item.get("predictedCategory"), category_set),
                title=item.get("title"),
                content=item.get("content", ""),
                parent=ParentRef(),  # root
                evidence=_evidence_refs(item, segments),
            ))
        elif result == "ATTACH":
            target = str(judgment.get("attachTo"))
            parent = (
                ParentRef(newParentItemId=target) if target in item_ids
                else ParentRef(existingNodeId=target)
            )
            commands.append(Command(
                op=_ATTACH_OP_BY_TYPE[ntype],
                itemId=item_id,
                sortKey=sort_key,
                nodeType=NodeType(ntype),
                category=_coerce_category(item.get("predictedCategory"), category_set),
                title=item.get("title"),
                content=item.get("content", ""),
                parent=parent,
                evidence=_evidence_refs(item, segments),
            ))
        elif result == "UNATTACHED":
            # M2: 연결할 이번 회의 결정 없음/미확정 → 노드로 보존(graph_state=UNATTACHED, root).
            commands.append(Command(
                op=_CREATE_OP_BY_TYPE[ntype],
                itemId=item_id,
                sortKey=sort_key,
                nodeType=NodeType(ntype),
                category=_coerce_category(item.get("predictedCategory"), category_set),
                title=item.get("title"),
                content=item.get("content", ""),
                parent=ParentRef(),  # root (부모 없음)
                graphState=GraphState.UNATTACHED,
                evidence=_evidence_refs(item, segments),
            ))
        elif result == "UPDATE_ACTION":
            target = str(judgment.get("targetActionId"))
            commands.append(Command(
                op=PlanOp.UPDATE_ACTION,
                itemId=item_id,
                sortKey=sort_key,
                targetActionId=target,
                changes=dict(judgment.get("changes") or {}),
                expectedVersion=action_versions.get(target),
            ))
        else:  # MINUTES_ONLY
            commands.append(Command(
                op=PlanOp.RECORD_MINUTES,
                itemId=item_id,
                sortKey=sort_key,
                reason=str(judgment.get("reason") or "NO_RELATED_DECISION"),
            ))

    commands.sort(key=lambda c: c.sortKey.as_tuple())
    return ChangePlan(
        planId=plan_id,
        projectId=project_id,
        externalMeetingId=external_meeting_id,
        requestId=request_id,
        lineage=lineage,
        commands=commands,
    )


# --- 규칙 7: 기술적 중복 시그니처 --------------------------------------------
def source_key(project_id: str, external_meeting_id: str, item_id: str) -> tuple[str, str, str]:
    """node UNIQUE(project_id, source_meeting_id, source_item_id) 자연키."""
    return (project_id, external_meeting_id, item_id)


def title_evidence_signature(title: str, evidence: list[EvidenceRef]) -> tuple[str, tuple[str, ...]]:
    """동일 제목·근거 중복 감지용 시그니처 (IF-5 rule 7)."""
    segs = tuple(sorted({ev.segmentId for ev in evidence}))
    return (normalize_quote(title or ""), segs)
