"""계약 단위 테스트 — 열거값 분리, 전이표(상태 세탁), 부모 규칙, Change Plan 검증, lineage."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from data_pipeline.contracts import (
    ChangePlan,
    Command,
    Lineage,
    NodeType,
    ParentRef,
    PlanOp,
    SortKey,
    default_lifecycle_status,
    parent_rule_violation,
    transition_allowed,
)


def test_lifecycle_terminal_blocks_laundering():
    # COMPLETED/CANCELLED terminal → 어떤 전이도 불가 (경유 우회 차단).
    assert transition_allowed("ACTION", "TODO", "IN_PROGRESS")
    assert transition_allowed("ACTION", "IN_PROGRESS", "COMPLETED")
    assert not transition_allowed("ACTION", "COMPLETED", "IN_PROGRESS")
    assert not transition_allowed("ACTION", "COMPLETED", "CANCELLED")
    assert not transition_allowed("ACTION", "CANCELLED", "IN_PROGRESS")
    # 같은 상태 no-op 은 멱등 허용.
    assert transition_allowed("ACTION", "COMPLETED", "COMPLETED")


def test_parent_rules():
    assert parent_rule_violation("DECISION", None, "ACTIVE") is None
    assert parent_rule_violation("DECISION", "DECISION", "ACTIVE") is not None  # root 여야
    assert parent_rule_violation("ACTION", "DECISION", "ACTIVE") is None
    assert parent_rule_violation("ACTION", "ACTION", "ACTIVE") is not None
    assert parent_rule_violation("ISSUE", "DECISION", "ACTIVE") is None
    assert parent_rule_violation("ISSUE", "ACTION", "ACTIVE") is None
    assert parent_rule_violation("ISSUE", None, "ACTIVE") is not None
    # UNATTACHED 는 부모 없어야.
    assert parent_rule_violation("ACTION", None, "UNATTACHED") is None
    assert parent_rule_violation("ACTION", "DECISION", "UNATTACHED") is not None


def test_default_lifecycle_status():
    assert default_lifecycle_status("DECISION") == "ACTIVE"
    assert default_lifecycle_status("ACTION") == "TODO"
    assert default_lifecycle_status("ISSUE") == "OPEN"


def test_parent_ref_exclusive():
    with pytest.raises(ValidationError):
        ParentRef(newParentItemId="m1", existingNodeId="node-1")
    assert ParentRef().is_root()


def test_command_shape_validation():
    sk = SortKey(startMs=0, segmentId="seg-1", itemId="m1")
    # CREATE 는 nodeType/title/evidence 필요.
    with pytest.raises(ValidationError):
        Command(op=PlanOp.CREATE_DECISION, itemId="m1", sortKey=sk)
    # UPDATE_ACTION 은 target+changes 필요.
    with pytest.raises(ValidationError):
        Command(op=PlanOp.UPDATE_ACTION, itemId="m1", sortKey=sk)
    ok = Command(op=PlanOp.UPDATE_ACTION, itemId="m1", sortKey=sk,
                 targetActionId="node-1", changes={"status": "COMPLETED"})
    assert ok.targetActionId == "node-1"


def test_change_plan_sorts_by_sort_key():
    lineage = Lineage()
    c_late = Command(op=PlanOp.RECORD_MINUTES, itemId="mB", reason="NOT_CONFIRMED",
                     sortKey=SortKey(startMs=9000, segmentId="seg-9", itemId="mB"))
    c_early = Command(op=PlanOp.RECORD_MINUTES, itemId="mA", reason="NOT_CONFIRMED",
                      sortKey=SortKey(startMs=1000, segmentId="seg-1", itemId="mA"))
    plan = ChangePlan(planId="p", projectId="proj", externalMeetingId="M", requestId="r",
                      lineage=lineage, commands=[c_late, c_early])
    order = [c.itemId for c in plan.sorted_commands()]
    assert order == ["mA", "mB"]  # LLM 배열 순서(mB,mA) 가 아니라 evidence 시각 순서
