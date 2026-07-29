"""gold 어댑터 변환 규칙 (오프라인, LLM 없음) — 회의 간 판정 → UNATTACHED."""

from __future__ import annotations

from evaluation.gold_adapter import adapt_gold_judgments


def test_m2x_cross_meeting_attach_becomes_unattached():
    exp = adapt_gold_judgments("M2X")
    # 기존 결정(D-M1-03 등) ATTACH → UNATTACHED
    assert exp["m1"].result == "UNATTACHED" and exp["m1"].origin == "ATTACH"
    assert exp["m10"].result == "UNATTACHED"
    # 회의 내 신규 결정 + 그 하위 ATTACH 는 유지
    assert exp["m6"].result == "NEW_DECISION"
    assert exp["m7"].result == "ATTACH" and exp["m7"].parent_item_id == "m6"
    # MINUTES_ONLY → UNATTACHED (reason 보존)
    assert exp["m9"].result == "UNATTACHED" and exp["m9"].reason == "NOT_CONFIRMED"


def test_m2y_update_action_becomes_unattached():
    exp = adapt_gold_judgments("M2Y")
    assert exp["m1"].result == "UNATTACHED" and exp["m1"].origin == "UPDATE_ACTION"
    assert exp["m4"].result == "UNATTACHED" and exp["m4"].origin == "UPDATE_ACTION"
    # 회의 간 기존 결정/액션 ATTACH 도 UNATTACHED
    assert exp["m2"].result == "UNATTACHED"
    assert exp["m3"].result == "UNATTACHED"


def test_m1_within_meeting_preserved():
    exp = adapt_gold_judgments("M1")
    assert exp["m1"].result == "NEW_DECISION"
    assert exp["m2"].result == "ATTACH" and exp["m2"].parent_item_id == "m1"
    assert exp["m5"].result == "UNATTACHED"  # gold MINUTES_ONLY
