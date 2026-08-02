import type { TreeNodeInput } from "../page/Project/Tree/components/SpaceTree";

/**
 * 노드 API가 붙기 전까지 쓰는 샘플 트리 — 지금은 성능 확인용으로 1000개 규모다.
 *
 * id는 위치(c1-d2-t3-i4)로 자동 생성한다. 손으로 쓰면 중복이 나기 쉽고,
 * id는 레이아웃 시드라 중복되면 노드가 겹치거나 사라진다.
 * 개수는 아래 BULK 값만 줄이면 바로 작아진다.
 */

const CATEGORY_NAMES = [
  "Frontend",
  "Backend",
  "AI",
  "Infra",
  "Design",
  "Planning",
];

/** 자식 수를 인덱스로 흔들어 준다 — 전부 같으면 격자처럼 보이고 반지름 변화도 안 드러난다 */
const BULK = {
  decisionsPerCategory: (categoryIndex: number) => 5 + (categoryIndex % 2),
  tasksPerDecision: (decisionIndex: number) => 4 + (decisionIndex % 3),
  issuesPerTask: (taskIndex: number) => 3 + (taskIndex % 5),
};

const DECISION_POOL = [
  "소셜 로그인 도입",
  "상태 관리 전략",
  "화상 회의 스택 선정",
  "데이터 모델링",
  "배포 환경 구성",
  "디자인 시스템 정의",
  "요약 모델 선정",
  "캐싱 전략",
];

const TASK_POOL = [
  "OAuth 연동",
  "로그인 상태 유지",
  "전역 스토어 설계",
  "회의방 API 설계",
  "STT 파이프라인 구성",
  "Docker Compose 구성",
  "컴포넌트 명세",
  "백로그 정리",
  "CI 파이프라인",
  "권한 검사 미들웨어",
];

const ISSUE_POOL = [
  "콜백 리다이렉트 처리",
  "세션 유지 방식",
  "새로고침 시 깜빡임",
  "서버 상태와 캐시 동기화",
  "화자 분리 정확도",
  "CORS 설정",
  "빌드 시간 단축",
  "계층 조회 성능",
  "다크 모드 대응",
  "우선순위 기준",
  "동시 종료 처리",
  "환각 방지",
];

/** 풀을 한 바퀴 돌면 뒤에 번호를 붙여 제목이 겹쳐 보이지 않게 한다 */
const pick = (pool: string[], index: number) => {
  const round = Math.floor(index / pool.length);
  const title = pool[index % pool.length];
  return round === 0 ? title : `${title} ${round + 1}`;
};

const buildCategory = (name: string, categoryIndex: number): TreeNodeInput => {
  const categoryId = `c${categoryIndex + 1}`;
  const decisionCount = BULK.decisionsPerCategory(categoryIndex);

  return {
    id: categoryId,
    type: "category",
    title: name,
    children: Array.from({ length: decisionCount }, (_, decisionIndex) => {
      const decisionId = `${categoryId}-d${decisionIndex + 1}`;
      const taskCount = BULK.tasksPerDecision(decisionIndex);

      return {
        id: decisionId,
        type: "decision" as const,
        title: pick(DECISION_POOL, decisionIndex),
        children: Array.from({ length: taskCount }, (_, taskIndex) => {
          const taskId = `${decisionId}-t${taskIndex + 1}`;
          const issueCount = BULK.issuesPerTask(taskIndex);

          return {
            id: taskId,
            type: "task" as const,
            title: pick(TASK_POOL, taskIndex),
            children: Array.from({ length: issueCount }, (_, issueIndex) => ({
              id: `${taskId}-i${issueIndex + 1}`,
              type: "issue" as const,
              title: pick(ISSUE_POOL, issueIndex),
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
  children: CATEGORY_NAMES.map(buildCategory),
};
