"""validation 단위 테스트 — 규칙 1~6 + evidence."""

from __future__ import annotations

from data_pipeline.validation import SegmentInfo, resolve_item_evidence, validate_judgments


def _segments():
    return {
        "seg-1": SegmentInfo(text="소음 전처리는 클로바 STT 전에 넣는 걸로 결정합시다.", start_ms=1000),
        "seg-2": SegmentInfo(text="그 전처리 필터는 이번 주에 제가 구현할게요.", start_ms=5000),
        "seg-3": SegmentInfo(text="네.", start_ms=9000),
    }


# --- evidence (규칙 4) --------------------------------------------------------
def test_evidence_min_length_blocks_short_quote():
    res = resolve_item_evidence(
        {"id": "m1", "evidence": [{"segmentId": "seg-3", "quote": "네."}]}, _segments()
    )
    assert not res.valid
    assert any("too short" in p for p in res.problems)


def test_evidence_requires_substring_and_offset():
    res = resolve_item_evidence(
        {"id": "m1", "evidence": [{"segmentId": "seg-1", "quote": "소음 전처리는 클로바 STT 전에 넣는 걸로 결정합시다."}]},
        _segments(),
    )
    assert res.valid
    assert res.resolved[0].char_start == 0  # 서버 오프셋 역산
    assert res.earliest_start_ms == 1000


def test_evidence_missing_segment():
    res = resolve_item_evidence(
        {"id": "m1", "evidence": [{"segmentId": "nope", "quote": "some long enough quote here"}]},
        _segments(),
    )
    assert not res.valid


# --- 판정 (규칙 1,2,3,5,6) ----------------------------------------------------
def _items():
    return [
        {"id": "m1", "type": "DECISION"},
        {"id": "m2", "type": "ACTION"},
        {"id": "m3", "type": "ISSUE"},
    ]


def _valid_evidence_segments():
    return {
        "seg-1": SegmentInfo("소음 전처리는 클로바 STT 전에 넣는 걸로 결정합시다.", 1000),
        "seg-2": SegmentInfo("그 전처리 필터는 이번 주에 제가 구현할게요.", 5000),
        "seg-3": SegmentInfo("리프레시 토큰 재사용 공격도 반드시 막아야 합니다.", 9000),
    }


def _items_with_evidence():
    return [
        {"id": "m1", "type": "DECISION", "evidence": [{"segmentId": "seg-1", "quote": "소음 전처리는 클로바 STT 전에 넣는 걸로 결정합시다."}]},
        {"id": "m2", "type": "ACTION", "evidence": [{"segmentId": "seg-2", "quote": "그 전처리 필터는 이번 주에 제가 구현할게요."}]},
        {"id": "m3", "type": "ISSUE", "evidence": [{"segmentId": "seg-3", "quote": "리프레시 토큰 재사용 공격도 반드시 막아야 합니다."}]},
    ]


def test_coverage_fills_missing_with_minutes_only():
    result = validate_judgments(
        items=_items_with_evidence(),
        raw_judgments=[{"itemId": "m1", "result": "NEW_DECISION", "category": "BACKEND"}],
        decision_candidate_ids=set(), action_candidate_ids=set(),
        segments=_valid_evidence_segments(),
    )
    by_id = {j["itemId"]: j for j in result.judgments}
    assert set(by_id) == {"m1", "m2", "m3"}
    assert "m2" in result.filled and "m3" in result.filled
    assert by_id["m2"]["result"] == "MINUTES_ONLY"


def test_duplicate_itemid_invalidates_response():
    result = validate_judgments(
        items=_items_with_evidence(),
        raw_judgments=[
            {"itemId": "m1", "result": "NEW_DECISION", "category": "BACKEND"},
            {"itemId": "m1", "result": "MINUTES_ONLY", "reason": "NOT_CONFIRMED"},
        ],
        decision_candidate_ids=set(), action_candidate_ids=set(),
        segments=_valid_evidence_segments(),
    )
    assert result.response_invalid is not None
    assert all(j["result"] == "MINUTES_ONLY" for j in result.judgments)


def test_result_not_allowed_for_type_demoted():
    # DECISION 에 ATTACH 는 불가 → 강등.
    result = validate_judgments(
        items=[{"id": "m1", "type": "DECISION", "evidence": [{"segmentId": "seg-1", "quote": "소음 전처리는 클로바 STT 전에 넣는 걸로 결정합시다."}]}],
        raw_judgments=[{"itemId": "m1", "result": "ATTACH", "attachTo": "m9"}],
        decision_candidate_ids=set(), action_candidate_ids=set(),
        segments=_valid_evidence_segments(),
    )
    assert result.judgments[0]["result"] == "MINUTES_ONLY"
    assert any(d["rule"] == "RESULT_NOT_ALLOWED_FOR_TYPE" for d in result.demoted)


def test_out_of_candidate_attach_demoted():
    result = validate_judgments(
        items=[{"id": "m1", "type": "ISSUE", "evidence": [{"segmentId": "seg-3", "quote": "리프레시 토큰 재사용 공격도 반드시 막아야 합니다."}]}],
        raw_judgments=[{"itemId": "m1", "result": "ATTACH", "attachTo": "decision-999"}],
        decision_candidate_ids=set(), action_candidate_ids=set(),
        segments=_valid_evidence_segments(),
    )
    assert result.judgments[0]["result"] == "MINUTES_ONLY"
    assert any(d["rule"] == "ATTACH_TARGET_NOT_IN_CANDIDATES" for d in result.demoted)


def test_issue_attach_to_minutes_only_parent_demoted():
    # m2(ACTION) 가 MINUTES_ONLY 인데 m3(ISSUE) 가 m2 에 attach → 부모가 MINUTES_ONLY → 강등.
    result = validate_judgments(
        items=_items_with_evidence(),
        raw_judgments=[
            {"itemId": "m1", "result": "NEW_DECISION", "category": "BACKEND"},
            {"itemId": "m2", "result": "MINUTES_ONLY", "reason": "NOT_CONFIRMED"},
            {"itemId": "m3", "result": "ATTACH", "attachTo": "m2"},
        ],
        decision_candidate_ids=set(), action_candidate_ids=set(),
        segments=_valid_evidence_segments(),
    )
    by_id = {j["itemId"]: j for j in result.judgments}
    assert by_id["m3"]["result"] == "MINUTES_ONLY"
    assert any(d["rule"] == "ATTACH_TO_MINUTES_ONLY" for d in result.demoted)


def test_update_action_status_key_is_rejected():
    # lifecycle 제거(0007) 후 "status" 는 허용 키가 아니다 → 강등.
    result = validate_judgments(
        items=[{"id": "m1", "type": "ACTION", "evidence": [{"segmentId": "seg-2", "quote": "그 전처리 필터는 이번 주에 제가 구현할게요."}]}],
        raw_judgments=[{"itemId": "m1", "result": "UPDATE_ACTION", "targetActionId": "A-1",
                        "changes": {"status": "IN_PROGRESS"}}],
        decision_candidate_ids=set(), action_candidate_ids={"A-1"},
        segments=_valid_evidence_segments(),
    )
    assert result.judgments[0]["result"] == "MINUTES_ONLY"


def test_update_action_due_date_is_still_allowed():
    result = validate_judgments(
        items=[{"id": "m1", "type": "ACTION", "evidence": [{"segmentId": "seg-2", "quote": "그 전처리 필터는 이번 주에 제가 구현할게요."}]}],
        raw_judgments=[{"itemId": "m1", "result": "UPDATE_ACTION", "targetActionId": "A-1",
                        "changes": {"dueDate": "2026-09-01"}}],
        decision_candidate_ids=set(), action_candidate_ids={"A-1"},
        segments=_valid_evidence_segments(),
    )
    assert result.judgments[0]["result"] == "UPDATE_ACTION"


def test_sequential_order_uses_evidence_time_not_array_order():
    # 배열은 [늦은, 이른] 이지만 정렬 키는 evidence startMs 순.
    items = [
        {"id": "mLate", "type": "ACTION", "evidence": [{"segmentId": "seg-3", "quote": "리프레시 토큰 재사용 공격도 반드시 막아야 합니다."}]},
        {"id": "mEarly", "type": "ACTION", "evidence": [{"segmentId": "seg-1", "quote": "소음 전처리는 클로바 STT 전에 넣는 걸로 결정합시다."}]},
    ]
    result = validate_judgments(
        items=items, raw_judgments=[], decision_candidate_ids=set(),
        action_candidate_ids=set(), segments=_valid_evidence_segments(),
    )
    assert result.sequential_order == ["mEarly", "mLate"]
