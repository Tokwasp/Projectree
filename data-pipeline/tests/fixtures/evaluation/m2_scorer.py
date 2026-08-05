"""M2 회귀 채점기 (경량, 자체 구현 — 동결 PoC 채점기와 별개).

지표:
  - 추출 coverage / 1:1 F1  (예측 item ↔ gold item 매칭: evidence 세그먼트 Jaccard + 제목 유사도)
  - 확정성 판정 정확도       (NEW_DECISION vs UNATTACHED, 매칭된 항목 대상)
  - result class 정확도       (NEW_DECISION / ATTACH / UNATTACHED 정확 일치)
  - 회의 내 attach 정확도     (gold 기대 ATTACH 항목이 예측도 ATTACH + 부모 매칭)
매칭은 gold↔예측 항목 사이 evidence 세그먼트 집합의 Jaccard 최대 그리디(동률 시 제목 difflib).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .gold_adapter import ExpectedJudgment

_MATCH_THRESHOLD = 0.30


def _seg_set(item: dict) -> set[str]:
    return {e.get("segmentId") for e in (item.get("evidence") or []) if e.get("segmentId")}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b) if (a | b) else 0.0


def _title_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a or "", b or "").ratio()


def match_items(gold_items: list[dict], pred_items: list[dict]) -> dict[str, str]:
    """gold itemId → pred itemId 매칭 (그리디 1:1). 매칭 안 되면 키 없음."""
    pairs = []
    for g in gold_items:
        gseg = _seg_set(g)
        for p in pred_items:
            score = _jaccard(gseg, _seg_set(p))
            if score == 0.0:
                continue
            tie = _title_sim(g.get("title", ""), p.get("title", ""))
            pairs.append((score, tie, str(g["id"]), str(p["id"])))
    pairs.sort(reverse=True)
    used_g: set[str] = set()
    used_p: set[str] = set()
    mapping: dict[str, str] = {}
    for score, _tie, gid, pid in pairs:
        if score < _MATCH_THRESHOLD or gid in used_g or pid in used_p:
            continue
        mapping[gid] = pid
        used_g.add(gid)
        used_p.add(pid)
    return mapping


_CONFIRMED = {"NEW_DECISION", "ATTACH"}


def _confirmation_class(result: str) -> str:
    return "CONFIRMED" if result in _CONFIRMED else "UNATTACHED"


@dataclass
class MeetingScore:
    meeting_id: str
    gold_count: int
    pred_count: int
    matched: int
    coverage_recall: float
    coverage_precision: float
    coverage_f1: float
    result_class_accuracy: float
    confirmation_accuracy: float
    within_attach_total: int
    within_attach_correct: int
    detail: dict = field(default_factory=dict)

    @property
    def within_attach_accuracy(self) -> float:
        return self.within_attach_correct / self.within_attach_total if self.within_attach_total else 1.0


def score_meeting(
    meeting_id: str,
    gold_items: list[dict],
    expected: dict[str, ExpectedJudgment],
    pred_items: list[dict],
    pred_disposition: dict[str, dict],
) -> MeetingScore:
    """pred_disposition[predItemId] = {"result": ..., "parentItemId": ...} (DB 반영 결과에서 파생)."""
    mapping = match_items(gold_items, pred_items)
    matched = len(mapping)
    gold_n, pred_n = len(gold_items), len(pred_items)
    recall = matched / gold_n if gold_n else 0.0
    precision = matched / pred_n if pred_n else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    result_ok = conf_ok = 0
    attach_total = attach_ok = 0
    rows = []
    for gid, exp in expected.items():
        pid = mapping.get(gid)
        pred = pred_disposition.get(pid, {}) if pid else {}
        pred_result = pred.get("result", "NONE")
        rc = pred_result == exp.result
        cc = _confirmation_class(pred_result) == _confirmation_class(exp.result)
        result_ok += int(rc)
        conf_ok += int(cc)
        if exp.result == "ATTACH":
            attach_total += 1
            gold_parent_pred = mapping.get(exp.parent_item_id or "")
            if pred_result == "ATTACH" and pred.get("parentItemId") == gold_parent_pred and gold_parent_pred:
                attach_ok += 1
        rows.append({"goldId": gid, "expected": exp.result, "origin": exp.origin,
                     "predId": pid, "pred": pred_result, "resultOk": rc})

    n_exp = len(expected) or 1
    return MeetingScore(
        meeting_id=meeting_id, gold_count=gold_n, pred_count=pred_n, matched=matched,
        coverage_recall=round(recall, 3), coverage_precision=round(precision, 3), coverage_f1=round(f1, 3),
        result_class_accuracy=round(result_ok / n_exp, 3),
        confirmation_accuracy=round(conf_ok / n_exp, 3),
        within_attach_total=attach_total, within_attach_correct=attach_ok,
        detail={"rows": rows},
    )
