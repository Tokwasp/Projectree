"""계약 단위 테스트 — 열거값 분리, 전이표(상태 세탁), 부모 규칙, Change Plan 검증, lineage."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from data_pipeline.contracts import (
    ChangePlan,
    Command,
    CompleteInitialReviewCommand,
    EditUnattachedNodeCommand,
    ReanalyzeUnattachedNodeCommand,
    ApproveCreateNewCommand,
    ApproveLinkExistingCommand,
    ApproveMergeExistingCommand,
    Lineage,
    NodeType,
    ParentRef,
    PlanOp,
    RelationType,
    SortKey,
    CHANGES_ALLOWED_KEYS,
    allowed_parent_types,
    is_allowed_parent_type,
    parent_rule_violation,
    analysis_run_status_transition_allowed,
    analysis_status_transition_allowed,
)


def test_is_allowed_parent_type_is_the_single_type_rule():
    """§5.3: Decision 은 root, Action→Decision, Issue→Decision|Action."""

    assert is_allowed_parent_type("DECISION", None)
    assert not is_allowed_parent_type("DECISION", "DECISION")

    assert is_allowed_parent_type("ACTION", "DECISION")
    assert not is_allowed_parent_type("ACTION", "ACTION")
    assert not is_allowed_parent_type("ACTION", "ISSUE")
    assert not is_allowed_parent_type("ACTION", None)

    assert is_allowed_parent_type("ISSUE", "DECISION")
    assert is_allowed_parent_type("ISSUE", "ACTION")
    assert not is_allowed_parent_type("ISSUE", "ISSUE")
    assert not is_allowed_parent_type("ISSUE", None)

    assert not is_allowed_parent_type("UNKNOWN", "DECISION")


def test_allowed_parent_types_matches_the_validator():
    assert allowed_parent_types("DECISION") == frozenset()
    assert allowed_parent_types("ACTION") == frozenset({"DECISION"})
    assert allowed_parent_types("ISSUE") == frozenset({"DECISION", "ACTION"})


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
    assert RelationType.RELATED_TO.value == "RELATED_TO"


def test_update_action_can_no_longer_carry_a_status():
    """lifecycle 제거(0007) 이후 UPDATE_ACTION 은 dueDate 만 바꾼다."""

    assert "status" not in CHANGES_ALLOWED_KEYS
    assert CHANGES_ALLOWED_KEYS == frozenset({"dueDate"})


def test_analysis_status_contracts():
    assert analysis_status_transition_allowed("PENDING", "ANALYZING")
    assert analysis_status_transition_allowed("ANALYZING", "ANALYZED")
    assert analysis_status_transition_allowed("ANALYZED", "STALE")
    assert analysis_status_transition_allowed("STALE", "PENDING")
    assert analysis_status_transition_allowed("FAILED", "PENDING")
    assert not analysis_status_transition_allowed("ANALYZED", "PENDING")

    assert analysis_run_status_transition_allowed("PENDING", "RUNNING")
    assert analysis_run_status_transition_allowed("RUNNING", "COMPLETED")
    assert analysis_run_status_transition_allowed("RUNNING", "FAILED")
    assert analysis_run_status_transition_allowed(
        "COMPLETED",
        "SUPERSEDED",
    )
    assert not analysis_run_status_transition_allowed("FAILED", "RUNNING")


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


def test_initial_and_final_review_command_contracts_use_uuid_and_versions():
    source_id = uuid.uuid4()
    target_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    initial = CompleteInitialReviewCommand(
        candidateId=source_id,
        expectedVersion=2,
    )
    assert initial.candidateId == source_id

    create = ApproveCreateNewCommand(
        sourceNodeId=source_id,
        sourceExpectedVersion=3,
        analysisRunId=analysis_id,
    )
    assert create.analysisRunId == analysis_id

    link = ApproveLinkExistingCommand(
        sourceNodeId=source_id,
        targetNodeId=target_id,
        relationType="RELATED_TO",
        sourceExpectedVersion=3,
        targetExpectedVersion=7,
        analysisRunId=analysis_id,
    )
    assert link.relationType.value == "RELATED_TO"

    merge = ApproveMergeExistingCommand(
        sourceNodeId=source_id,
        targetNodeId=target_id,
        mergedTitle="최종 제목",
        mergedContent="최종 본문",
        sourceExpectedVersion=3,
        targetExpectedVersion=7,
        analysisRunId=analysis_id,
    )
    assert merge.targetNodeId == target_id

    with pytest.raises(ValidationError):
        CompleteInitialReviewCommand(
            candidateId="not-a-uuid",
            expectedVersion=1,
        )
    with pytest.raises(ValidationError):
        ApproveCreateNewCommand(
            sourceNodeId=source_id,
            sourceExpectedVersion=0,
            analysisRunId=analysis_id,
        )

    edit = EditUnattachedNodeCommand(
        nodeId=source_id,
        expectedVersion=2,
        title="수정된 제목",
    )
    assert edit.title == "수정된 제목"
    reanalyze = ReanalyzeUnattachedNodeCommand(
        nodeId=source_id,
        expectedVersion=2,
    )
    assert reanalyze.nodeId == source_id
    with pytest.raises(ValidationError, match="at least one"):
        EditUnattachedNodeCommand(
            nodeId=source_id,
            expectedVersion=2,
        )
