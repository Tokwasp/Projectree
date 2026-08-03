"""서버 하드 검증 (LLM ② 판정) — PoC v3_runner.server_validate_judgments 규칙 수확.

담는 규칙:
  1. itemId 유일성        — 판정 응답에 중복 itemId → 응답 무효(전부 MINUTES_ONLY 강등)
  2. 후보 allowlist        — 기존 노드 참조(attachTo/targetActionId)는 후보 목록에만
  3. 부모 유효성           — m* attach 의 부모 타입/상태(ACTION→새 DECISION, ISSUE→새 DECISION|ATTACH ACTION)
  4. evidence (evidence.py) — 실존/부분 문자열/최소 10자. 무효 evidence 항목은 그래프 반영 불가 → 강등
  6. 순차 적용             — evidence 최초 startMs→segmentId→itemId 순서로 running 상태 갱신(LLM 배열 순서 금지)
그리고 커버리지(모든 itemId 정확히 1회, 누락은 MINUTES_ONLY 로 채움) + 허용 판정/필드 규칙.

원칙: 잘못된 그래프 반영이 누락보다 나쁘다 → 애매하면 MINUTES_ONLY 강등.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from data_pipeline.contracts.enums import (
    ALLOWED_RESULTS_BY_TYPE,
    CHANGES_ALLOWED_KEYS,
    JudgmentResult,
    NodeType,
    result_allowed_for_type,
)

from .evidence import SegmentInfo, resolve_item_evidence

_MINUTES_ONLY = JudgmentResult.MINUTES_ONLY.value
_NEW_DECISION = JudgmentResult.NEW_DECISION.value
_ATTACH = JudgmentResult.ATTACH.value
_UPDATE = JudgmentResult.UPDATE_ACTION.value
_UNATTACHED = JudgmentResult.UNATTACHED.value


@dataclass
class ValidationResult:
    judgments: list[dict]                     # 최종 판정 (item 원래 순서)
    demoted: list[dict] = field(default_factory=list)
    filled: list[str] = field(default_factory=list)
    dropped: list[dict] = field(default_factory=list)
    invalid_evidence: list[dict] = field(default_factory=list)
    sequential_order: list[str] = field(default_factory=list)
    response_invalid: str | None = None       # 응답 전체 무효 사유(규칙 1)


def field_violations(judgment: dict) -> list[str]:
    """result 별 필드 존재/부재 규칙 (PoC judgment_field_violations 재작성)."""
    result = str(judgment.get("result"))
    category = judgment.get("category")
    attach_to = judgment.get("attachTo")
    reason = judgment.get("reason")
    target = judgment.get("targetActionId")
    changes = judgment.get("changes")
    v: list[str] = []

    if result != _UPDATE:
        if target:
            v.append(f"{result} must not carry targetActionId")
        if changes:
            v.append(f"{result} must not carry changes")

    if result == _NEW_DECISION:
        if not category:
            v.append("NEW_DECISION requires category")
        if attach_to:
            v.append("NEW_DECISION must not carry attachTo")
        if reason:
            v.append("NEW_DECISION must not carry reason")
    elif result == _ATTACH:
        if not attach_to:
            v.append("ATTACH requires attachTo")
        if category:
            v.append("ATTACH must not carry category")
        if reason:
            v.append("ATTACH must not carry reason")
    elif result == _UPDATE:
        if not target:
            v.append("UPDATE_ACTION requires targetActionId")
        if not changes:
            v.append("UPDATE_ACTION requires changes")
        else:
            bad = set(changes) - CHANGES_ALLOWED_KEYS
            if bad:
                v.append(f"UPDATE_ACTION changes has disallowed keys: {sorted(bad)}")
        if category:
            v.append("UPDATE_ACTION must not carry category")
        if attach_to:
            v.append("UPDATE_ACTION must not carry attachTo")
        if reason:
            v.append("UPDATE_ACTION must not carry reason")
    elif result in (_MINUTES_ONLY, _UNATTACHED):
        if not reason:
            v.append(f"{result} requires reason")
        if category:
            v.append(f"{result} must not carry category")
        if attach_to:
            v.append(f"{result} must not carry attachTo")
    else:
        v.append(f"unknown judgment result '{result}'")
    return v


def _sequential_order(items: list[dict], segments: dict[str, SegmentInfo]) -> tuple[list[str], dict[str, dict]]:
    """규칙 6: evidence 최초 startMs → segmentId → itemId 로 정렬. LLM 배열 순서 사용 금지."""
    keyed = []
    resolutions: dict[str, dict] = {}
    for item in items:
        res = resolve_item_evidence(item, segments)
        resolutions[res.item_id] = {
            "valid": res.valid,
            "problems": res.problems,
            "earliest_start_ms": res.earliest_start_ms,
            "earliest_segment_id": res.earliest_segment_id,
        }
        start = res.earliest_start_ms if res.earliest_start_ms is not None else 2_147_483_647
        seg = res.earliest_segment_id or ""
        keyed.append(((start, seg, res.item_id), res.item_id))
    keyed.sort(key=lambda pair: pair[0])
    return [item_id for _, item_id in keyed], resolutions


def validate_judgments(
    *,
    items: list[dict],
    raw_judgments: list[dict],
    decision_candidate_ids: set[str],
    action_candidate_ids: set[str],
    segments: dict[str, SegmentInfo],
) -> ValidationResult:
    item_type = {str(it.get("id")): str(it.get("type")).upper() for it in items}
    item_order = [str(it.get("id")) for it in items]
    seq_order, resolutions = _sequential_order(items, segments)

    demoted: list[dict] = []
    filled: list[str] = []
    dropped: list[dict] = []
    invalid_evidence: list[dict] = []

    # 규칙 1: 판정 응답 itemId 유일성. 중복이면 응답 무효 → 전부 MINUTES_ONLY.
    seen: set[str] = set()
    duplicate = None
    for j in raw_judgments:
        iid = str(j.get("itemId"))
        if iid in seen:
            duplicate = iid
            break
        seen.add(iid)
    if duplicate is not None:
        judgments = [
            {"itemId": iid, "result": _MINUTES_ONLY, "reason": "LOW_CONFIDENCE"} for iid in item_order
        ]
        for iid in item_order:
            demoted.append({"itemId": iid, "from": None, "rule": "DUPLICATE_ITEMID_RESPONSE_INVALID"})
        return ValidationResult(
            judgments=judgments, demoted=demoted, filled=[], dropped=[],
            invalid_evidence=[], sequential_order=seq_order,
            response_invalid=f"duplicate itemId {duplicate!r} in judgment response",
        )

    chosen: dict[str, dict] = {}
    for j in raw_judgments:
        iid = str(j.get("itemId"))
        if iid not in item_type:
            dropped.append({"itemId": iid, "rule": "UNKNOWN_ITEM"})
            continue
        chosen[iid] = dict(j)

    # 커버리지: 누락 item 은 MINUTES_ONLY 로 채운다 (누락보다 기록이 낫다).
    for iid in item_order:
        if iid not in chosen:
            chosen[iid] = {"itemId": iid, "result": _MINUTES_ONLY, "reason": "NO_RELATED_DECISION"}
            filled.append(iid)

    def demote(iid: str, rule: str, reason: str = "NO_RELATED_DECISION") -> None:
        original = chosen[iid].get("result")
        chosen[iid] = {"itemId": iid, "result": _MINUTES_ONLY, "reason": reason}
        demoted.append({"itemId": iid, "from": original, "rule": rule})

    # 규칙 4: evidence 무효 항목은 그래프 반영 불가 → 강등.
    for iid in item_order:
        res = resolutions.get(iid, {"valid": False, "problems": ["no resolution"]})
        if not res["valid"]:
            invalid_evidence.append({"itemId": iid, "problems": res["problems"]})

    # UPDATE_ACTION 이 참조할 수 있는 기존 Action id allowlist (규칙 2).
    action_ids = set(action_candidate_ids)

    # 1차: 독립 규칙 + UPDATE 순차 적용 + 기존-id allowlist. seq_order 로 순회.
    for iid in seq_order:
        if iid in filled:
            continue
        judgment = chosen[iid]
        result = str(judgment.get("result"))
        ntype = item_type[iid]

        if not result_allowed_for_type(result, ntype):
            demote(iid, "RESULT_NOT_ALLOWED_FOR_TYPE", "LOW_CONFIDENCE")
            continue
        violations = field_violations(judgment)
        if violations:
            demote(iid, "FIELD_VIOLATION:" + ";".join(violations), "LOW_CONFIDENCE")
            continue
        # 그래프 반영(NEW_DECISION/ATTACH/UPDATE)인데 evidence 무효면 강등.
        if result != _MINUTES_ONLY and not resolutions.get(iid, {}).get("valid"):
            demote(iid, "EVIDENCE_INVALID", "LOW_CONFIDENCE")
            continue

        if result == _UPDATE:
            target = str(judgment.get("targetActionId"))
            if target not in action_ids:  # 규칙 2
                demote(iid, "UPDATE_TARGET_NOT_IN_CANDIDATES")
                continue
        elif result == _ATTACH:
            target = str(judgment.get("attachTo"))
            if target in item_type:
                continue  # m* → 2차 fixpoint 에서 검증
            # 기존 노드 참조 (규칙 2 allowlist).
            if target in action_ids:
                if ntype != NodeType.ISSUE.value:  # 기존 액션에는 ISSUE 만 붙는다
                    demote(iid, "ACTION_ATTACH_TO_EXISTING_ACTION")
            elif target in decision_candidate_ids:
                pass  # 기존 결정에 ATTACH — 허용
            else:
                demote(iid, "ATTACH_TARGET_NOT_IN_CANDIDATES")

    # 2차: m* attach 대상 존재/부모 타입/부모 MINUTES_ONLY 를 fixpoint 로 검증 (규칙 3).
    changed = True
    while changed:
        changed = False
        for iid in item_order:
            judgment = chosen[iid]
            if str(judgment.get("result")) != _ATTACH:
                continue
            target = str(judgment.get("attachTo"))
            if target not in item_type:
                continue  # 기존-id 는 1차에서 처리
            ntype = item_type[iid]
            rule: str | None = None
            parent = chosen.get(target, {})
            parent_type = item_type.get(target)
            parent_result = str(parent.get("result"))
            if parent_type is None:
                rule = "ATTACH_M_TARGET_MISSING"
            elif parent_result == _MINUTES_ONLY:
                rule = "ATTACH_TO_MINUTES_ONLY"
            elif ntype == NodeType.ACTION.value:
                if not (parent_type == NodeType.DECISION.value and parent_result == _NEW_DECISION):
                    rule = "ACTION_PARENT_INVALID"
            elif ntype == NodeType.ISSUE.value:
                decision_parent = parent_type == NodeType.DECISION.value and parent_result == _NEW_DECISION
                action_parent = parent_type == NodeType.ACTION.value and parent_result == _ATTACH
                if not (decision_parent or action_parent):
                    rule = "ISSUE_PARENT_INVALID"
            else:
                rule = "ATTACH_FROM_DECISION"
            if rule:
                demote(iid, rule)
                changed = True

    return ValidationResult(
        judgments=[chosen[iid] for iid in item_order],
        demoted=demoted,
        filled=filled,
        dropped=dropped,
        invalid_evidence=invalid_evidence,
        sequential_order=seq_order,
    )
