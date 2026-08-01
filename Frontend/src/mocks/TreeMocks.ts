import type { TreeNodeInput } from "../page/Project/Tree/components/SpaceTree";

/**
 * 노드 API가 붙기 전까지 우주 공간을 확인하기 위한 샘플 트리.
 * 계층은 root(프로젝트) → category(6종 고정) → decision → task → issue 다.
 */
export const mockProjectTree: TreeNodeInput = {
  id: "root",
  type: "root",
  title: "Projectree",
  children: [
    {
      id: "category-frontend",
      type: "category",
      title: "Frontend",
      children: [
        {
          id: "decision-auth",
          type: "decision",
          title: "소셜 로그인 도입",
          children: [
            {
              id: "task-oauth",
              type: "task",
              title: "OAuth 연동",
              children: [
                {
                  id: "issue-callback",
                  type: "issue",
                  title: "콜백 리다이렉트 처리",
                },
                { id: "issue-session", type: "issue", title: "세션 유지 방식" },
              ],
            },
            {
              id: "task-login-persist",
              type: "task",
              title: "로그인 상태 유지",
              children: [
                {
                  id: "issue-refresh-flicker",
                  type: "issue",
                  title: "새로고침 시 깜빡임",
                },
              ],
            },
          ],
        },
        {
          id: "decision-state",
          type: "decision",
          title: "상태 관리 전략",
          children: [
            {
              id: "task-store",
              type: "task",
              title: "전역 스토어 설계",
              children: [
                {
                  id: "issue-cache-sync",
                  type: "issue",
                  title: "서버 상태와 캐시 동기화",
                },
              ],
            },
          ],
        },
      ],
    },
    {
      id: "category-backend",
      type: "category",
      title: "Backend",
      children: [
        {
          id: "decision-meeting-stack",
          type: "decision",
          title: "화상 회의 스택 선정",
          children: [
            {
              id: "task-livekit",
              type: "task",
              title: "LiveKit 연동",
              children: [
                {
                  id: "issue-track-handoff",
                  type: "issue",
                  title: "프리조인 트랙 인계",
                },
              ],
            },
            { id: "task-room-api", type: "task", title: "회의방 API 설계" },
          ],
        },
      ],
    },
    {
      id: "category-ai",
      type: "category",
      title: "AI",
      children: [
        {
          id: "decision-summary-model",
          type: "decision",
          title: "회의록 요약 모델 선정",
          children: [
            {
              id: "task-stt",
              type: "task",
              title: "STT 파이프라인 구성",
              children: [
                {
                  id: "issue-speaker-split",
                  type: "issue",
                  title: "화자 분리 정확도",
                },
              ],
            },
          ],
        },
      ],
    },
    {
      id: "category-infra",
      type: "category",
      title: "Infra",
      children: [
        {
          id: "decision-deploy",
          type: "decision",
          title: "배포 환경 구성",
          children: [
            {
              id: "task-compose",
              type: "task",
              title: "Docker Compose 구성",
              children: [
                { id: "issue-cors", type: "issue", title: "CORS 설정" },
              ],
            },
          ],
        },
      ],
    },
    {
      id: "category-design",
      type: "category",
      title: "Design",
      children: [
        {
          id: "decision-design-system",
          type: "decision",
          title: "디자인 시스템 정의",
          children: [
            { id: "task-color-token", type: "task", title: "컬러 토큰 정리" },
          ],
        },
      ],
    },
    {
      id: "category-planning",
      type: "category",
      title: "Planning",
      children: [
        {
          id: "decision-sprint-scope",
          type: "decision",
          title: "스프린트 범위 확정",
          children: [
            { id: "task-backlog", type: "task", title: "백로그 정리" },
          ],
        },
      ],
    },
  ],
};
