"""gold 어댑터 — 회의 간 판정을 M2(회의 내 전용) 기대값으로 변환.

M2 ②는 기존 결정·액션을 보지 않으므로(§2 역할 경계), gold 의 회의 간 판정은 M2 에서 성립할 수
없다. PoC "검색 X" 조건과 동일 논리로 **UNATTACHED 로 변환**해 채점한다. gold 원본은 수정하지 않고,
변환 규칙만 코드로 명시한다.

변환 규칙 (gold result → M2 기대 result):
  NEW_DECISION                          → NEW_DECISION
  ATTACH, attachTo = 이번 회의 itemId(m*) → ATTACH (회의 내)
  ATTACH, attachTo = 기존 D-*/A-*        → UNATTACHED (NO_RELATED_DECISION)  # 회의 간 → M3
  UPDATE_ACTION                          → UNATTACHED (NO_RELATED_DECISION)  # 회의 간 → M3
  MINUTES_ONLY                           → UNATTACHED (reason 보존: NOT_CONFIRMED, 그 외 → NO_RELATED_DECISION)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

FROZEN = Path(__file__).resolve().parent / "poc_frozen"
GOLD_DIR = FROZEN / "gold"
MEETINGS_DIR = FROZEN / "meetings"


@dataclass
class ExpectedJudgment:
    item_id: str
    result: str                       # NEW_DECISION / ATTACH / UNATTACHED
    parent_item_id: str | None = None  # ATTACH 인 경우 이번 회의 부모 itemId
    reason: str | None = None
    origin: str = ""                   # 원래 gold result (추적용)


def load_segments(meeting_id: str) -> list[dict]:
    return json.loads((MEETINGS_DIR / f"{meeting_id}_segments.json").read_text(encoding="utf-8"))["segments"]


def load_gold_items(meeting_id: str) -> list[dict]:
    return json.loads((GOLD_DIR / f"{meeting_id}_items_gold.json").read_text(encoding="utf-8"))["items"]


def load_gold_judgments(meeting_id: str) -> list[dict]:
    return json.loads((GOLD_DIR / f"{meeting_id}_judgments_gold.json").read_text(encoding="utf-8"))["judgments"]


def adapt_gold_judgments(meeting_id: str) -> dict[str, ExpectedJudgment]:
    """gold 판정을 M2 기대값으로 변환해 {itemId: ExpectedJudgment} 로 반환."""
    items = load_gold_items(meeting_id)
    item_ids = {str(it["id"]) for it in items}
    expected: dict[str, ExpectedJudgment] = {}
    for j in load_gold_judgments(meeting_id):
        iid = str(j["itemId"])
        result = j["result"]
        if result == "NEW_DECISION":
            expected[iid] = ExpectedJudgment(iid, "NEW_DECISION", origin=result)
        elif result == "ATTACH":
            target = str(j.get("attachTo"))
            if target in item_ids:  # 이번 회의 내 연결
                expected[iid] = ExpectedJudgment(iid, "ATTACH", parent_item_id=target, origin=result)
            else:  # 기존 노드 연결 → 회의 간 → M2 에서는 UNATTACHED
                expected[iid] = ExpectedJudgment(iid, "UNATTACHED", reason="NO_RELATED_DECISION", origin=result)
        elif result == "UPDATE_ACTION":
            expected[iid] = ExpectedJudgment(iid, "UNATTACHED", reason="NO_RELATED_DECISION", origin=result)
        elif result == "MINUTES_ONLY":
            reason = j.get("reason")
            reason = "NOT_CONFIRMED" if reason == "NOT_CONFIRMED" else "NO_RELATED_DECISION"
            expected[iid] = ExpectedJudgment(iid, "UNATTACHED", reason=reason, origin=result)
        else:
            expected[iid] = ExpectedJudgment(iid, "UNATTACHED", reason="NO_RELATED_DECISION", origin=result)
    return expected
