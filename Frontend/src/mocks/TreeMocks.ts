import type { TreeNodeInput } from "../page/Project/Tree/components/SpaceTree";

/**
 * 노드 API가 붙기 전까지 쓰는 샘플 트리.
 * id는 위치(c1-d2-t3)로 자동 생성한다 — 손으로 쓰면 중복이 나기 쉽고,
 * id는 레이아웃 시드라 중복되면 노드가 겹치거나 사라진다.
 */

interface TaskSpec {
  title: string;
  issues?: string[];
}

interface DecisionSpec {
  title: string;
  tasks: TaskSpec[];
}

interface CategorySpec {
  title: string;
  decisions: DecisionSpec[];
}

const CATEGORIES: CategorySpec[] = [
  {
    title: "Frontend",
    decisions: [
      {
        title: "소셜 로그인 도입",
        tasks: [
          {
            title: "OAuth 연동",
            issues: ["콜백 리다이렉트 처리", "세션 유지 방식"],
          },
          { title: "로그인 상태 유지", issues: ["새로고침 시 깜빡임"] },
          { title: "로그아웃 처리" },
        ],
      },
      {
        title: "상태 관리 전략",
        tasks: [
          { title: "전역 스토어 설계", issues: ["서버 상태와 캐시 동기화"] },
          { title: "폼 상태 분리" },
        ],
      },
      {
        title: "회의 화면 구현",
        tasks: [
          { title: "프리조인 모달", issues: ["트랙 인계 시점"] },
          {
            title: "그리드 레이아웃",
            issues: ["스크롤 제거", "화면공유 스포트라이트"],
          },
          { title: "미니 창", issues: ["드래그 경계 계산"] },
        ],
      },
      // 반지름이 자식 수에 따라 늘어나는지 확인하려고 일부러 자식을 많이 붙였다
      {
        title: "컴포넌트 리팩터링",
        tasks: [
          { title: "버튼 통합" },
          { title: "모달 공통화" },
          { title: "폼 필드 추출" },
          { title: "아이콘 정리" },
          { title: "레이아웃 정리" },
          { title: "테이블 공통화" },
          { title: "토스트 도입" },
          { title: "스켈레톤 적용" },
          { title: "에러 바운더리" },
          { title: "라우팅 정리" },
          { title: "훅 네이밍 통일" },
          { title: "CSS 토큰 정리" },
        ],
      },
    ],
  },
  {
    title: "Backend",
    decisions: [
      {
        title: "화상 회의 스택 선정",
        tasks: [
          {
            title: "LiveKit 연동",
            issues: ["프리조인 트랙 인계", "토큰 발급 권한"],
          },
          { title: "회의방 API 설계", issues: ["동시 종료 처리"] },
          { title: "웹훅 수신" },
        ],
      },
      {
        title: "인증 방식 결정",
        tasks: [
          { title: "세션 기반 인증", issues: ["CORS 쿠키 전달"] },
          { title: "권한 검사 미들웨어" },
        ],
      },
      {
        title: "데이터 모델링",
        tasks: [
          { title: "노드 테이블 설계", issues: ["계층 조회 성능"] },
          { title: "회의록 저장 구조" },
          { title: "프로젝트 멤버 관계" },
        ],
      },
    ],
  },
  {
    title: "AI",
    decisions: [
      {
        title: "회의록 요약 모델 선정",
        tasks: [
          {
            title: "STT 파이프라인 구성",
            issues: ["화자 분리 정확도", "실시간 처리 지연"],
          },
          { title: "요약 프롬프트 설계", issues: ["환각 방지"] },
        ],
      },
      {
        title: "노드 자동 추출",
        tasks: [
          { title: "결정사항 분류", issues: ["오분류 처리"] },
          { title: "이슈 추출" },
          { title: "카테고리 매핑" },
        ],
      },
    ],
  },
  {
    title: "Infra",
    decisions: [
      {
        title: "배포 환경 구성",
        tasks: [
          {
            title: "Docker Compose 구성",
            issues: ["CORS 설정", "볼륨 권한"],
          },
          { title: "CI 파이프라인", issues: ["빌드 시간 단축"] },
          { title: "환경변수 분리" },
        ],
      },
      {
        title: "모니터링 도입",
        tasks: [{ title: "로그 수집" }, { title: "알림 설정" }],
      },
    ],
  },
  {
    title: "Design",
    decisions: [
      {
        title: "디자인 시스템 정의",
        tasks: [
          { title: "컴포넌트 명세", issues: ["반응형 기준"] },
          { title: "아이콘 세트" },
          { title: "타이포 스케일" },
        ],
      },
      {
        title: "우주 트리 컨셉",
        tasks: [
          { title: "노드 색상 체계", issues: ["타입 구분 명확성"] },
          { title: "라벨 가독성", issues: ["줌아웃 시 정리"] },
        ],
      },
    ],
  },
  {
    title: "Planning",
    decisions: [
      {
        title: "스프린트 범위 확정",
        tasks: [
          { title: "백로그 정리", issues: ["우선순위 기준"] },
          { title: "일정 산정" },
        ],
      },
      {
        title: "발표 준비",
        tasks: [
          { title: "시연 시나리오" },
          { title: "데모 데이터 준비" },
          { title: "발표 자료" },
        ],
      },
    ],
  },
];

const buildCategory = (
  category: CategorySpec,
  categoryIndex: number,
): TreeNodeInput => {
  const categoryId = `c${categoryIndex + 1}`;

  return {
    id: categoryId,
    type: "category",
    title: category.title,
    children: category.decisions.map((decision, decisionIndex) => {
      const decisionId = `${categoryId}-d${decisionIndex + 1}`;

      return {
        id: decisionId,
        type: "decision" as const,
        title: decision.title,
        children: decision.tasks.map((task, taskIndex) => {
          const taskId = `${decisionId}-t${taskIndex + 1}`;

          return {
            id: taskId,
            type: "task" as const,
            title: task.title,
            children: task.issues?.map((issue, issueIndex) => ({
              id: `${taskId}-i${issueIndex + 1}`,
              type: "issue" as const,
              title: issue,
            })),
          };
        }),
      };
    }),
  };
};

export const mockProjectTree: TreeNodeInput = {
  id: "root",
  type: "root",
  title: "Projectree",
  children: CATEGORIES.map(buildCategory),
};
