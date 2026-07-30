"""v2.2 계약 열거값 + 상태 전이표 + 부모 규칙.

핵심 분리 (v2.2):
  - graph_state    : 그래프상 위치/가시성 (ACTIVE/UNATTACHED/EXCLUDED/MERGED/ARCHIVED)
  - lifecycle_status: 노드 자체의 도메인 상태 (타입별로 다름)

두 축은 독립이다. 예: Action 이 lifecycle COMPLETED 여도 graph_state 는 ACTIVE 일 수 있다.
"""

from __future__ import annotations

from enum import Enum


class NodeType(str, Enum):
    DECISION = "DECISION"
    ACTION = "ACTION"
    ISSUE = "ISSUE"


class GraphState(str, Enum):
    ACTIVE = "ACTIVE"          # 그래프에 정상 편입 (부모 규칙 적용)
    UNATTACHED = "UNATTACHED"  # 노드로 존재하나 부모 없음 (parent_id = NULL)
    EXCLUDED = "EXCLUDED"      # 제안됐으나 미채택 (— 미채택)
    MERGED = "MERGED"          # 중복으로 다른 노드에 병합됨
    ARCHIVED = "ARCHIVED"      # 사용자 보관


class AnalysisStatus(str, Enum):
    """Node가 가리키는 최신 분석의 요약 상태."""

    PENDING = "PENDING"
    ANALYZING = "ANALYZING"
    ANALYZED = "ANALYZED"
    STALE = "STALE"
    FAILED = "FAILED"


class AnalysisRunStatus(str, Enum):
    """불변에 가까운 개별 분석 실행의 수명주기."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SUPERSEDED = "SUPERSEDED"


ANALYSIS_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    AnalysisStatus.PENDING.value: frozenset(
        {
            AnalysisStatus.ANALYZING.value,
            AnalysisStatus.FAILED.value,
            AnalysisStatus.STALE.value,
        }
    ),
    AnalysisStatus.ANALYZING.value: frozenset(
        {
            AnalysisStatus.ANALYZED.value,
            AnalysisStatus.FAILED.value,
            AnalysisStatus.STALE.value,
        }
    ),
    AnalysisStatus.ANALYZED.value: frozenset({AnalysisStatus.STALE.value}),
    AnalysisStatus.STALE.value: frozenset({AnalysisStatus.PENDING.value}),
    AnalysisStatus.FAILED.value: frozenset(
        {AnalysisStatus.PENDING.value, AnalysisStatus.STALE.value}
    ),
}

ANALYSIS_RUN_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    AnalysisRunStatus.PENDING.value: frozenset(
        {
            AnalysisRunStatus.RUNNING.value,
            AnalysisRunStatus.FAILED.value,
            AnalysisRunStatus.SUPERSEDED.value,
        }
    ),
    AnalysisRunStatus.RUNNING.value: frozenset(
        {
            AnalysisRunStatus.COMPLETED.value,
            AnalysisRunStatus.FAILED.value,
            AnalysisRunStatus.SUPERSEDED.value,
        }
    ),
    AnalysisRunStatus.COMPLETED.value: frozenset(
        {AnalysisRunStatus.SUPERSEDED.value}
    ),
    AnalysisRunStatus.FAILED.value: frozenset(),
    AnalysisRunStatus.SUPERSEDED.value: frozenset(),
}


def analysis_status_transition_allowed(from_status: str, to_status: str) -> bool:
    if from_status == to_status:
        return from_status in {value.value for value in AnalysisStatus}
    return to_status in ANALYSIS_STATUS_TRANSITIONS.get(
        from_status,
        frozenset(),
    )


def analysis_run_status_transition_allowed(
    from_status: str,
    to_status: str,
) -> bool:
    if from_status == to_status:
        return from_status in {value.value for value in AnalysisRunStatus}
    return to_status in ANALYSIS_RUN_STATUS_TRANSITIONS.get(
        from_status,
        frozenset(),
    )


# --- 타입별 lifecycle_status ---------------------------------------------------
class DecisionStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


class ActionStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class IssueStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


# --- 관계 (AI 추론 아님 — 사용자/후속 파이프라인이 생성) -----------------------
class RelationType(str, Enum):
    ATTACHED_TO = "ATTACHED_TO"  # confirmed child -> confirmed parent
    RELATED_TO = "RELATED_TO"    # undirected semantic relation; not a structural parent
    SAME = "SAME"              # 중복 후보도 이 타입 + status=PROPOSED 로 표현 (별도 타입 금지)
    REVERSES = "REVERSES"
    FOLLOWS = "FOLLOWS"
    RESOLVED_BY = "RESOLVED_BY"


class RelationStatus(str, Enum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


# --- LLM ② 판정 (IF-4) --------------------------------------------------------
class JudgmentResult(str, Enum):
    """Internal server judgment commands.

    The frozen PoC LLM contract is defined separately as PocJudgmentResult and
    does not contain UNATTACHED.  UNATTACHED here is server-derived only.
    """
    NEW_DECISION = "NEW_DECISION"
    ATTACH = "ATTACH"
    UPDATE_ACTION = "UPDATE_ACTION"  # 기존 액션 상태·기한 갱신 (M1 apply / M3 ②)
    UNATTACHED = "UNATTACHED"        # server-derived preservation command; not emitted by PoC LTS LLM
    MINUTES_ONLY = "MINUTES_ONLY"    # 서버 강등(무효 evidence 등, 노드 미생성)의 내부 disposition


class MinutesReason(str, Enum):
    NO_RELATED_DECISION = "NO_RELATED_DECISION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    NOT_CONFIRMED = "NOT_CONFIRMED"


# --- 집합/맵 ------------------------------------------------------------------
NODE_TYPES = frozenset(v.value for v in NodeType)

LIFECYCLE_STATUSES_BY_TYPE: dict[str, frozenset[str]] = {
    NodeType.DECISION.value: frozenset(v.value for v in DecisionStatus),
    NodeType.ACTION.value: frozenset(v.value for v in ActionStatus),
    NodeType.ISSUE.value: frozenset(v.value for v in IssueStatus),
}

# UPDATE_ACTION changes 로 바꿀 수 있는 키 (PoC 2차: assignee 는 화자 특정 불가로 MVP 제외).
CHANGES_ALLOWED_KEYS = frozenset({"status", "dueDate"})

# type별 허용 판정. UNATTACHED 는 M2 회의 내 판정 공간, UPDATE_ACTION/MINUTES_ONLY 는 M1/M3.
ALLOWED_RESULTS_BY_TYPE: dict[str, frozenset[str]] = {
    NodeType.DECISION.value: frozenset(
        {JudgmentResult.NEW_DECISION.value, JudgmentResult.UNATTACHED.value, JudgmentResult.MINUTES_ONLY.value}
    ),
    NodeType.ACTION.value: frozenset(
        {JudgmentResult.ATTACH.value, JudgmentResult.UPDATE_ACTION.value,
         JudgmentResult.UNATTACHED.value, JudgmentResult.MINUTES_ONLY.value}
    ),
    NodeType.ISSUE.value: frozenset(
        {JudgmentResult.ATTACH.value, JudgmentResult.UNATTACHED.value, JudgmentResult.MINUTES_ONLY.value}
    ),
}

GRAPH_RESULTS = frozenset({JudgmentResult.NEW_DECISION.value, JudgmentResult.ATTACH.value})


# --- lifecycle 전이표: 상태 세탁 차단 (COMPLETED/CANCELLED terminal) -----------
# from_status -> 허용되는 to_status 집합. 없는 키(=terminal)는 어떤 전이도 불가.
LIFECYCLE_TRANSITIONS: dict[str, dict[str, frozenset[str]]] = {
    NodeType.DECISION.value: {
        DecisionStatus.ACTIVE.value: frozenset({DecisionStatus.SUPERSEDED.value}),
        DecisionStatus.SUPERSEDED.value: frozenset(),  # terminal
    },
    NodeType.ACTION.value: {
        ActionStatus.TODO.value: frozenset(
            {ActionStatus.IN_PROGRESS.value, ActionStatus.COMPLETED.value, ActionStatus.CANCELLED.value}
        ),
        ActionStatus.IN_PROGRESS.value: frozenset(
            {ActionStatus.COMPLETED.value, ActionStatus.CANCELLED.value}
        ),
        ActionStatus.COMPLETED.value: frozenset(),   # terminal — 되살리기 금지 (R9)
        ActionStatus.CANCELLED.value: frozenset(),    # terminal
    },
    NodeType.ISSUE.value: {
        IssueStatus.OPEN.value: frozenset({IssueStatus.RESOLVED.value}),
        IssueStatus.RESOLVED.value: frozenset({IssueStatus.OPEN.value}),  # 재오픈은 세탁 아님
    },
}

TERMINAL_STATUSES: dict[str, frozenset[str]] = {
    NodeType.ACTION.value: frozenset({ActionStatus.COMPLETED.value, ActionStatus.CANCELLED.value}),
    NodeType.DECISION.value: frozenset({DecisionStatus.SUPERSEDED.value}),
    NodeType.ISSUE.value: frozenset(),
}


def default_lifecycle_status(node_type: str) -> str:
    """새로 생성되는 노드의 초기 lifecycle_status."""
    return {
        NodeType.DECISION.value: DecisionStatus.ACTIVE.value,
        NodeType.ACTION.value: ActionStatus.TODO.value,
        NodeType.ISSUE.value: IssueStatus.OPEN.value,
    }[node_type]


def lifecycle_status_valid(node_type: str, status: str) -> bool:
    return status in LIFECYCLE_STATUSES_BY_TYPE.get(node_type, frozenset())


def transition_allowed(node_type: str, from_status: str, to_status: str) -> bool:
    """상태 세탁 차단 규칙. 같은 상태로의 no-op 은 허용(멱등)."""
    table = LIFECYCLE_TRANSITIONS.get(node_type)
    if table is None:
        return False
    if from_status not in table or not lifecycle_status_valid(node_type, to_status):
        return False
    if from_status == to_status:
        return True
    return to_status in table[from_status]


def result_allowed_for_type(result: str, node_type: str) -> bool:
    return result in ALLOWED_RESULTS_BY_TYPE.get(node_type, frozenset())


# --- 부모 규칙 ----------------------------------------------------------------
# ACTIVE 노드의 (자식 type -> 허용되는 부모 type 집합). None 부모는 아래 함수에서 처리.
_ACTIVE_PARENT_RULES: dict[str, frozenset[str] | None] = {
    NodeType.DECISION.value: None,  # root — 부모 없음
    NodeType.ACTION.value: frozenset({NodeType.DECISION.value}),
    NodeType.ISSUE.value: frozenset({NodeType.DECISION.value, NodeType.ACTION.value}),
}


def parent_rule_violation(node_type: str, parent_type: str | None, graph_state: str) -> str | None:
    """부모 규칙 위반 사유를 반환 (없으면 None).

    - UNATTACHED: parent 없어야 함.
    - ACTIVE: Decision=root(부모 없음), Action->Decision, Issue->Decision|Action.
    - EXCLUDED/MERGED/ARCHIVED: 부모 유무를 강제하지 않음(과거 상태 보존).
    """
    if graph_state == GraphState.UNATTACHED.value:
        return None if parent_type is None else "UNATTACHED node must have no parent"
    if graph_state == GraphState.ACTIVE.value:
        allowed = _ACTIVE_PARENT_RULES.get(node_type, frozenset())
        if allowed is None:
            return None if parent_type is None else f"{node_type} must be root (no parent)"
        if parent_type is None:
            return f"{node_type} requires a parent"
        if parent_type not in allowed:
            return f"{node_type} parent must be one of {sorted(allowed)}, got {parent_type}"
        return None
    return None  # EXCLUDED/MERGED/ARCHIVED: 관대
