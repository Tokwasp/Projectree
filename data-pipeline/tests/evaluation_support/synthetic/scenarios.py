"""Pre-labelled, deterministic and realistic graph scenarios.

Labels are authored here before any Retrieval or model output is observed.
Changing a label requires a dataset-version bump and code review.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

DATASET_VERSION = "synthetic-gold-v1"
MAIN_PROJECT_ID = "synthetic-eval-main"
ISOLATION_PROJECT_ID = "synthetic-eval-isolation"
CASE_MEETING_ID = "synthetic-eval-cases"
_NAMESPACE = uuid.UUID("dd683f8e-a876-4bf2-a4c9-06d274e217e8")


def stable_uuid(project_id: str, kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(
        _NAMESPACE,
        f"{DATASET_VERSION}:{project_id}:{kind}:{key}",
    )


@dataclass(frozen=True)
class SyntheticNodeSpec:
    key: str
    project_id: str
    node_type: str
    category: str
    title: str
    content: str
    graph_state: str = "ACTIVE"
    parent_key: str | None = None
    meeting_id: str = "synthetic-canonical-01"

    @property
    def node_id(self) -> uuid.UUID:
        return stable_uuid(self.project_id, "node", self.key)

    @property
    def source_item_id(self) -> str:
        return f"syn-{self.key}"

    @property
    def segment_id(self) -> str:
        return f"seg-{self.key}"

    @property
    def quote(self) -> str:
        return (
            f"{self.title}. {self.content} "
            f"이 내용은 {DATASET_VERSION}에서 사전에 정의한 회의 근거입니다."
        )


@dataclass(frozen=True)
class SyntheticCaseSpec:
    case_id: str
    source: SyntheticNodeSpec
    expected_action: str
    expected_target_key: str | None
    expected_parent_key: str | None
    category: str
    notes: str
    provider_evaluation: bool = True


_DECISIONS = (
    ("authentication", "JWT 기반 인증 체계를 채택한다", "접근 토큰과 갱신 토큰을 분리하고 만료 정책을 적용한다.", "BACKEND"),
    ("release", "금요일 오후에 정기 배포한다", "스테이징 검증 후 운영 배포를 승인한다.", "INFRA"),
    ("search", "회의 검색에 의미 기반 검색을 사용한다", "키워드 검색과 벡터 검색을 함께 제공한다.", "AI"),
    ("notification", "중요 상태 변경은 실시간 알림으로 전달한다", "실패 알림과 사용자 알림 채널을 분리한다.", "BACKEND"),
    ("design-system", "공통 디자인 시스템을 우선 적용한다", "버튼과 입력 컴포넌트의 토큰을 통일한다.", "FRONTEND"),
    ("retention", "회의 원문은 90일간 보관한다", "Evidence 감사 정보는 정책에 따라 장기 보존한다.", "PLANNING"),
    ("observability", "분산 추적 식별자를 전 구간에 전파한다", "SQS부터 데이터베이스까지 요청 상관관계를 남긴다.", "INFRA"),
    ("quality-gate", "자동 병합은 보수적 안전 게이트를 통과해야 한다", "유사도와 margin 및 부모 일치를 모두 검사한다.", "AI"),
    ("mobile", "모바일 화면은 반응형 웹으로 먼저 제공한다", "별도 네이티브 앱은 후속 범위로 둔다.", "FRONTEND"),
    ("backup", "PostgreSQL 백업은 매일 수행한다", "복구 리허설을 월 1회 진행한다.", "INFRA"),
    ("privacy", "민감 발언은 권한이 있는 사용자만 조회한다", "프로젝트 격리와 감사 로그를 강제한다.", "BACKEND"),
    ("meeting-id", "Meeting ID 정본은 Spring이 발급한다", "OpenVidu 식별자는 매핑 테이블로 연결한다.", "DESIGN"),
    ("stt", "STT 원문과 정규화문을 함께 보존한다", "사용자 표시에는 정규화문을 사용하고 원문은 감사에 사용한다.", "AI"),
    ("outbox", "Spring 통지는 Outbox를 통해 발행한다", "DB 커밋과 이벤트 발행의 원자성을 보장한다.", "BACKEND"),
    ("rollout", "새 병합 정책은 단계적으로 활성화한다", "관찰 모드에서 오탐률을 확인한 뒤 자동 반영한다.", "PLANNING"),
)

_ACTIONS = (
    ("auth-api", "로그인 API를 구현한다", "JWT 발급과 갱신 및 로그아웃 처리를 구현한다.", "authentication", "BACKEND"),
    ("auth-test", "인증 통합 테스트를 작성한다", "토큰 만료와 재발급 경계를 PostgreSQL 통합 테스트로 검증한다.", "authentication", "BACKEND"),
    ("release-checklist", "배포 체크리스트를 자동화한다", "스테이징 헬스체크와 마이그레이션 상태를 검사한다.", "release", "INFRA"),
    ("vector-search", "pgvector 검색 쿼리를 구현한다", "동일 프로젝트와 상태 필터를 적용하고 Top-K를 반환한다.", "search", "AI"),
    ("alert-worker", "실패 알림 Worker를 구현한다", "재시도 소진 이벤트를 운영 채널로 전송한다.", "notification", "BACKEND"),
    ("button-kit", "공통 버튼 컴포넌트를 만든다", "크기와 상태 및 접근성 스타일을 토큰화한다.", "design-system", "FRONTEND"),
    ("retention-job", "원문 보관 만료 작업을 구현한다", "정책 만료 데이터를 감사 가능하게 정리한다.", "retention", "BACKEND"),
    ("trace-id", "SQS 메시지에 trace ID를 전파한다", "Worker와 LLM 호출 로그를 같은 ID로 묶는다.", "observability", "INFRA"),
    ("merge-calibration", "자동 병합 임계값을 보정한다", "CONFIRMED gold label로 precision과 recall을 계산한다.", "quality-gate", "AI"),
    ("responsive-layout", "회의 화면 반응형 레이아웃을 구현한다", "모바일과 태블릿 breakpoint를 검증한다.", "mobile", "FRONTEND"),
    ("backup-script", "PostgreSQL 백업 스크립트를 작성한다", "암호화한 백업과 보존 주기를 자동화한다.", "backup", "INFRA"),
    ("permission-filter", "프로젝트 권한 필터를 적용한다", "모든 Node 조회와 수정에 project_id를 강제한다.", "privacy", "BACKEND"),
    ("meeting-map", "Meeting ID 매핑 계약을 문서화한다", "Spring ID와 OpenVidu ID의 책임 경계를 정의한다.", "meeting-id", "DESIGN"),
    ("stt-dictionary", "STT 기술 용어 사전을 확장한다", "실패 사례를 variants로 추가하고 충돌을 검사한다.", "stt", "AI"),
    ("outbox-publisher", "Outbox Publisher를 구현한다", "선점과 재시도 및 멱등 발행을 지원한다.", "outbox", "BACKEND"),
    ("shadow-mode", "자동 병합 관찰 모드를 운영한다", "실제 반영 없이 추천과 정답 차이를 수집한다.", "rollout", "PLANNING"),
    ("api-rate-limit", "인증 API rate limit을 적용한다", "사용자와 IP 기준 제한을 조합한다.", "authentication", "BACKEND"),
    ("release-rollback", "배포 rollback 절차를 자동화한다", "실패한 버전을 안전하게 이전 버전으로 되돌린다.", "release", "INFRA"),
    ("search-filter", "검색 결과 상태 필터를 추가한다", "MERGED와 DELETED Node를 결과에서 제외한다.", "search", "AI"),
    ("notification-pref", "알림 수신 설정 화면을 만든다", "사용자가 채널과 이벤트를 선택하게 한다.", "notification", "FRONTEND"),
    ("input-kit", "공통 입력 컴포넌트를 만든다", "검증 오류와 도움말 표현을 통일한다.", "design-system", "FRONTEND"),
    ("retention-audit", "보관 정책 감사 보고서를 만든다", "삭제 대상과 보존 예외를 주기적으로 집계한다.", "retention", "PLANNING"),
    ("trace-dashboard", "분산 추적 대시보드를 구성한다", "구간별 P95 지연과 오류율을 시각화한다.", "observability", "INFRA"),
    ("false-merge-review", "오병합 검토 화면을 구현한다", "병합 근거와 원본 Evidence를 함께 표시한다.", "quality-gate", "FRONTEND"),
    ("rollout-metrics", "단계적 배포 지표를 정의한다", "오탐과 누락 및 사용자 취소율을 추적한다.", "rollout", "PLANNING"),
)

_ISSUES = (
    ("token-clock", "서버 시계 차이로 토큰 만료가 흔들린다", "NTP 오차와 만료 여유 시간을 확인해야 한다.", "authentication", "BACKEND"),
    ("deploy-lock", "동시 배포가 발생할 수 있다", "배포 잠금과 중복 실행 방지가 필요하다.", "release", "INFRA"),
    ("vector-drift", "임베딩 모델 변경 시 검색 품질이 흔들린다", "모델 버전별 재색인과 비교가 필요하다.", "search", "AI"),
    ("alert-storm", "연쇄 실패 시 알림 폭주 위험이 있다", "집계와 억제 정책이 필요하다.", "notification", "INFRA"),
    ("contrast", "일부 버튼의 대비가 접근성 기준에 못 미친다", "색상 토큰을 재검토해야 한다.", "design-system", "FRONTEND"),
    ("legal-hold", "법적 보존 요청은 일반 만료와 충돌한다", "예외 보존 플래그가 필요하다.", "retention", "PLANNING"),
    ("missing-trace", "외부 Provider 응답에 요청 ID가 없을 수 있다", "내부 상관 ID로 보완해야 한다.", "observability", "AI"),
    ("threshold-drift", "회의 유형별 최적 병합 임계값이 다르다", "단일 임계값의 한계를 측정해야 한다.", "quality-gate", "AI"),
    ("small-screen", "작은 화면에서 Evidence가 잘린다", "접기와 전체 보기 동작이 필요하다.", "mobile", "FRONTEND"),
    ("restore-time", "대용량 백업 복구 시간이 목표를 넘을 수 있다", "복구 시간 목표를 실측해야 한다.", "backup", "INFRA"),
)


def build_synthetic_nodes() -> list[SyntheticNodeSpec]:
    nodes: list[SyntheticNodeSpec] = []
    for index, (key, title, content, category) in enumerate(_DECISIONS, start=1):
        nodes.append(
            SyntheticNodeSpec(
                key=f"decision-{key}",
                project_id=MAIN_PROJECT_ID,
                node_type="DECISION",
                category=category,
                title=title,
                content=content,
                meeting_id=f"synthetic-canonical-{((index - 1) // 5) + 1:02d}",
            )
        )
    for index, (key, title, content, parent, category) in enumerate(_ACTIONS, start=1):
        nodes.append(
            SyntheticNodeSpec(
                key=f"action-{key}",
                project_id=MAIN_PROJECT_ID,
                node_type="ACTION",
                category=category,
                title=title,
                content=content,
                parent_key=f"decision-{parent}",
                meeting_id=f"synthetic-canonical-{((index - 1) // 5) + 4:02d}",
            )
        )
    for index, (key, title, content, parent, category) in enumerate(_ISSUES, start=1):
        nodes.append(
            SyntheticNodeSpec(
                key=f"issue-{key}",
                project_id=MAIN_PROJECT_ID,
                node_type="ISSUE",
                category=category,
                title=title,
                content=content,
                parent_key=f"decision-{parent}",
                meeting_id=f"synthetic-canonical-{((index - 1) // 5) + 9:02d}",
            )
        )
    return nodes


def _source(
    number: int,
    *,
    node_type: str,
    category: str,
    title: str,
    content: str,
    parent_key: str | None = None,
) -> SyntheticNodeSpec:
    return SyntheticNodeSpec(
        key=f"case-{number:03d}",
        project_id=MAIN_PROJECT_ID,
        node_type=node_type,
        category=category,
        title=title,
        content=content,
        graph_state="UNATTACHED",
        parent_key=parent_key,
        meeting_id=CASE_MEETING_ID,
    )


def build_synthetic_cases() -> list[SyntheticCaseSpec]:
    cases: list[SyntheticCaseSpec] = []
    merge_targets = [
        ("auth-api", "로그인과 토큰 재발급 API를 구현한다", "JWT 로그인 API 구현 범위가 동일하다."),
        ("auth-test", "인증 통합 테스트를 마무리한다", "토큰 만료와 재발급 테스트를 완료했다."),
        ("release-checklist", "배포 전 점검표를 자동화한다", "스테이징 헬스체크를 자동 실행한다."),
        ("vector-search", "pgvector 유사도 검색을 완성한다", "프로젝트 필터와 Top-K 검색 구현을 완료했다."),
        ("alert-worker", "실패 알림 워커를 개발한다", "재시도 소진 알림을 보내는 동일 업무다."),
        ("retention-job", "원문 만료 배치를 구현한다", "90일 만료 데이터를 정리하는 동일 작업이다."),
        ("trace-id", "메시지 trace ID 전파를 완료한다", "SQS와 LLM 로그 상관관계를 연결했다."),
        ("merge-calibration", "자동 병합 임계값 보정을 진행한다", "gold label로 threshold를 조정하는 동일 작업이다."),
        ("backup-script", "PostgreSQL 백업 자동화를 완료한다", "암호화 백업 스크립트를 배포했다."),
        ("stt-dictionary", "STT 용어 사전을 보강한다", "오인식 variants를 추가하는 동일 업무다."),
    ]
    for index, (target, title, content) in enumerate(merge_targets, start=1):
        target_row = next(row for row in _ACTIONS if row[0] == target)
        parent_key = f"decision-{target_row[3]}"
        cases.append(
            SyntheticCaseSpec(
                case_id=f"syn-{index:03d}",
                source=_source(
                    index,
                    node_type="ACTION",
                    category=target_row[4],
                    title=title,
                    content=content,
                    parent_key=parent_key,
                ),
                expected_action="MERGE",
                expected_target_key=f"action-{target}",
                expected_parent_key=parent_key,
                category="same-action-progress",
                notes="같은 Decision 아래 동일 Action의 재진술 또는 상태 전진",
            )
        )

    negatives = [
        ("로그인 화면 문구를 수정한다", "API 구현이 아니라 UI 카피 변경이다.", "FRONTEND", "decision-design-system"),
        ("인증 부하 테스트를 설계한다", "기존 통합 테스트와 완료 조건이 다르다.", "BACKEND", "decision-authentication"),
        ("배포 공지 템플릿을 만든다", "배포 체크리스트 자동화와 목적이 다르다.", "PLANNING", "decision-release"),
        ("검색 결과 UI 정렬을 개선한다", "pgvector 검색 쿼리와 별개의 프론트 업무다.", "FRONTEND", "decision-search"),
        ("사용자 마케팅 알림을 만든다", "실패 운영 알림 Worker와 목적이 다르다.", "BACKEND", "decision-notification"),
        ("보존 정책 안내 페이지를 만든다", "만료 배치 구현과 완료 조건이 다르다.", "FRONTEND", "decision-retention"),
        ("추적 ID 문서 예시를 작성한다", "실제 전파 구현과 별개인 문서 업무다.", "PLANNING", "decision-observability"),
        ("병합 화면 색상을 조정한다", "임계값 보정과 무관한 UI 작업이다.", "FRONTEND", "decision-quality-gate"),
        ("백업 비용 보고서를 작성한다", "백업 스크립트 구현과 목적이 다르다.", "PLANNING", "decision-backup"),
        ("일반 한글 맞춤법 사전을 추가한다", "STT 기술 용어 사전과 범위가 다르다.", "AI", "decision-stt"),
    ]
    for offset, (title, content, category, parent) in enumerate(negatives, start=11):
        cases.append(
            SyntheticCaseSpec(
                case_id=f"syn-{offset:03d}",
                source=_source(
                    offset,
                    node_type="ACTION",
                    category=category,
                    title=title,
                    content=content,
                    parent_key=parent,
                ),
                expected_action="CREATE_NEW",
                expected_target_key=None,
                expected_parent_key=parent,
                category="hard-negative",
                notes="키워드는 유사하지만 목적 또는 완료 조건이 다른 Action",
            )
        )

    fresh = [
        ("DECISION", "DESIGN", "GraphQL을 외부 조회 API로 채택한다", "REST 내부 API는 유지하고 외부 조회만 GraphQL로 제공한다.", None),
        ("DECISION", "INFRA", "장애 복구 리전을 별도로 둔다", "주 리전 장애 시 수동 전환 가능한 복구 리전을 준비한다.", None),
        ("ACTION", "FRONTEND", "회의 타임라인 인쇄 화면을 구현한다", "A4 출력에 맞춘 별도 레이아웃을 제공한다.", "decision-mobile"),
        ("ACTION", "AI", "회의 주제 분류 모델을 평가한다", "노드 병합과 별개의 주제 분류 정확도를 측정한다.", "decision-quality-gate"),
        ("ISSUE", "BACKEND", "대용량 Evidence 조회가 느리다", "페이지네이션과 인덱스 검토가 필요하다.", "decision-observability"),
    ]
    for offset, (node_type, category, title, content, parent) in enumerate(fresh, start=21):
        cases.append(
            SyntheticCaseSpec(
                case_id=f"syn-{offset:03d}",
                source=_source(
                    offset,
                    node_type=node_type,
                    category=category,
                    title=title,
                    content=content,
                    parent_key=parent,
                ),
                expected_action="CREATE_NEW",
                expected_target_key=None,
                expected_parent_key=parent,
                category="create-new",
                notes="기존 그래프에 없는 새 의미",
            )
        )

    decision_merges = [
        ("authentication", "인증은 JWT 토큰 방식을 사용하기로 한다"),
        ("search", "회의 검색은 벡터 의미 검색을 함께 사용한다"),
        ("stt", "STT 원본과 정규화 결과를 모두 저장한다"),
        ("outbox", "Spring 알림은 Outbox 패턴으로 전송한다"),
        ("rollout", "자동 병합은 단계적으로 출시한다"),
    ]
    for offset, (target, title) in enumerate(decision_merges, start=26):
        target_row = next(row for row in _DECISIONS if row[0] == target)
        cases.append(
            SyntheticCaseSpec(
                case_id=f"syn-{offset:03d}",
                source=_source(
                    offset,
                    node_type="DECISION",
                    category=target_row[3],
                    title=title,
                    content=target_row[2],
                ),
                expected_action="MERGE",
                expected_target_key=f"decision-{target}",
                expected_parent_key=None,
                category="decision-merge",
                notes="기존 Decision의 표현 변경",
            )
        )

    links = [
        ("authentication", "로그인 실패 횟수 지표를 추가한다", "BACKEND"),
        ("search", "검색 품질 대시보드를 만든다", "AI"),
        ("observability", "Provider 지연 경보를 추가한다", "INFRA"),
        ("privacy", "권한 변경 감사 화면을 만든다", "FRONTEND"),
    ]
    for offset, (target, title, category) in enumerate(links, start=31):
        cases.append(
            SyntheticCaseSpec(
                case_id=f"syn-{offset:03d}",
                source=_source(
                    offset,
                    node_type="ACTION",
                    category=category,
                    title=title,
                    content=f"{title}는 기존 Decision을 실행하기 위한 새 Action이다.",
                    parent_key=f"decision-{target}",
                ),
                expected_action="LINK",
                expected_target_key=f"decision-{target}",
                expected_parent_key=f"decision-{target}",
                category="link-parent",
                notes="새 Action을 기존 ACTIVE Decision에 ATTACHED_TO",
            )
        )

    safety = [
        # Category is a Graph partition: the same task in another Category is a
        # separate Node and must never be a MERGE target or a parent LINK.
        ("ACTION", "FRONTEND", "로그인 API를 구현한다", "BACKEND의 동일 제목 Action과 Category가 달라 병합 대상이 아니다.", "decision-authentication", "category-partition"),
        ("ACTION", "DESIGN", "pgvector 검색 쿼리를 구현한다", "AI Category의 동일 업무와 분리 저장되어야 한다.", "decision-search", "category-partition"),
        ("ISSUE", "AI", "pgvector 검색 쿼리를 구현한다", "제목은 같지만 Node 유형이 다르다.", "decision-search", "type-mismatch"),
        ("ACTION", "BACKEND", "로그인 API를 구현한다", "다른 프로젝트의 동명 Node는 target이 될 수 없다.", "decision-privacy", "parent-conflict"),
        ("ACTION", "INFRA", "배포 체크리스트를 자동화한다", "동일 제목이지만 실제 부모 Decision이 백업 정책이다.", "decision-backup", "parent-conflict"),
        ("DECISION", "PLANNING", "자동 병합은 항상 수행한다", "보수적 안전 게이트 Decision과 충돌한다.", None, "decision-conflict"),
    ]
    for offset, (node_type, category, title, content, parent, kind) in enumerate(safety, start=35):
        cases.append(
            SyntheticCaseSpec(
                case_id=f"syn-{offset:03d}",
                source=_source(
                    offset,
                    node_type=node_type,
                    category=category,
                    title=title,
                    content=content,
                    parent_key=parent,
                ),
                expected_action="CREATE_NEW",
                expected_target_key=None,
                expected_parent_key=parent,
                category=kind,
                notes="서버 안전 게이트가 MERGE를 허용하면 안 되는 사례",
                provider_evaluation=False,
            )
        )
    return cases


def build_isolation_nodes() -> list[SyntheticNodeSpec]:
    rows: list[SyntheticNodeSpec] = []
    for index in range(1, 9):
        target = build_synthetic_nodes()[15 + ((index - 1) % 10)]
        rows.append(
            SyntheticNodeSpec(
                key=f"isolation-{index:02d}",
                project_id=ISOLATION_PROJECT_ID,
                node_type=target.node_type,
                category=target.category,
                title=target.title,
                content=target.content,
                graph_state=(
                    "UNATTACHED"
                    if target.node_type in {"ACTION", "ISSUE"}
                    else "ACTIVE"
                ),
                meeting_id="synthetic-isolation-01",
            )
        )
    return rows


__all__ = [
    "CASE_MEETING_ID",
    "DATASET_VERSION",
    "ISOLATION_PROJECT_ID",
    "MAIN_PROJECT_ID",
    "SyntheticCaseSpec",
    "SyntheticNodeSpec",
    "build_isolation_nodes",
    "build_synthetic_cases",
    "build_synthetic_nodes",
    "stable_uuid",
]
