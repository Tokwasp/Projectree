"""v2.2 계약 열거값 + 상태 전이표 + 부모 규칙.

노드 상태 축은 graph_state 하나다.
  - graph_state: 그래프상 위치/가시성 (ACTIVE/UNATTACHED/EXCLUDED/MERGED/ARCHIVED)

Node 진행 상태는 팀 결정으로 제품에서 제외되었고
0007 Migration 에서 컬럼까지 제거되었다. 진행 상태를 다시 도입한다면
graph_state 와 독립된 새 축으로 설계한다.
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


class RetrievalStageStatus(str, Enum):
    """Durable result state for the Retrieval stage inside one Run."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class BModelStatus(str, Enum):
    """Durable state of the B-model stage inside one Analysis Run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"


class RecommendationType(str, Enum):
    CREATE_NEW = "CREATE_NEW"
    LINK = "LINK"
    MERGE = "MERGE"


class AnalysisCandidateStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


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

# UPDATE_ACTION changes 로 바꿀 수 있는 키 (PoC 2차: assignee 는 화자 특정 불가로 MVP 제외).
# "status" 는 Node 진행 상태 제거(0007)와 함께 빠졌다.
CHANGES_ALLOWED_KEYS = frozenset({"dueDate"})

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


def result_allowed_for_type(result: str, node_type: str) -> bool:
    return result in ALLOWED_RESULTS_BY_TYPE.get(node_type, frozenset())


# --- 부모 규칙 ----------------------------------------------------------------
# ACTIVE 노드의 (자식 type -> 허용되는 부모 type 집합). None 부모는 아래 함수에서 처리.
_ACTIVE_PARENT_RULES: dict[str, frozenset[str] | None] = {
    NodeType.DECISION.value: None,  # root — 부모 없음
    NodeType.ACTION.value: frozenset({NodeType.DECISION.value}),
    NodeType.ISSUE.value: frozenset({NodeType.DECISION.value, NodeType.ACTION.value}),
}


def is_allowed_parent_type(child_type: str, parent_type: str | None) -> bool:
    """타입만 보는 단일 부모 규칙.

    Decision 은 root, Action 은 Decision 만, Issue 는 Decision 또는 Action 을
    부모로 가진다. project/category 동일성, 부모의 ACTIVE·canonical 여부,
    단일 부모, self-parent·cycle 금지는 호출부에서 별도로 검증한다.
    """
    allowed = _ACTIVE_PARENT_RULES.get(child_type, frozenset())
    if allowed is None:
        return parent_type is None
    return parent_type is not None and parent_type in allowed


def allowed_parent_types(child_type: str) -> frozenset[str]:
    """child_type 이 부모로 가질 수 있는 타입 집합 (root 면 빈 집합)."""
    return _ACTIVE_PARENT_RULES.get(child_type) or frozenset()


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
