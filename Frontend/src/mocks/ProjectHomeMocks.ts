import type {
  ProjectHomeSummary,
  RecentDecisionSummary,
  RecentMeetingSummary,
} from "../types/ProjectHome";

export const mockProjectHome: ProjectHomeSummary = {
  projectId: 1,
  title: "Projectree 서비스 구축",
  description:
    "프로젝트의 진행 상황과 주요 정보를 체계적으로 관리하고, 회의와 결정사항을 한눈에 확인할 수 있는 협업 프로젝트입니다.",
};

export const mockRecentMeetings: RecentMeetingSummary[] = [
  {
    meetingId: 4,
    title: "개발 진행 상황 공유",
    scheduledAt: "2026-07-29T16:00:00",
    summary: "개발 진행 상황과 주요 이슈를 공유합니다.",
    hostName: "최싸피",
  },
  {
    meetingId: 3,
    title: "UI/UX 디자인 리뷰",
    scheduledAt: "2026-07-24T11:00:00",
    summary: "디자인 시안과 사용자 흐름을 점검했습니다.",
    hostName: "박싸피",
  },
  {
    meetingId: 2,
    title: "요구사항 검토 회의",
    scheduledAt: "2026-07-22T14:00:00",
    summary: "주요 기능과 사용자 요구사항을 검토했습니다.",
    hostName: "이싸피",
  },
  {
    meetingId: 1,
    title: "프로젝트 킥오프 회의",
    scheduledAt: "2026-07-20T10:00:00",
    summary: "프로젝트 목표와 범위, 팀원의 역할을 논의했습니다.",
    hostName: "김싸피",
  },
];

export const mockRecentDecisions: RecentDecisionSummary[] = [
  {
    decisionId: 1,
    title: "사용자 인증 방식을 소셜 로그인 기반으로 결정",
    sourceMeetingTitle: "요구사항 검토 회의",
    authorName: "이싸피",
    decidedAt: "2026-07-22T15:30:00",
  },
  {
    decisionId: 2,
    title: "메인 컬러를 디자인 시스템의 보라색으로 결정",
    sourceMeetingTitle: "UI/UX 디자인 리뷰",
    authorName: "박싸피",
    decidedAt: "2026-07-24T12:00:00",
  },
  {
    decisionId: 3,
    title: "프로젝트 목록 조회를 서버 페이지네이션으로 처리",
    sourceMeetingTitle: "개발 진행 상황 공유",
    authorName: "김싸피",
    decidedAt: "2026-07-25T10:00:00",
  },
  {
    decisionId: 4,
    title: "핵심 기능별 API와 Hook 책임 분리",
    sourceMeetingTitle: "개발 진행 상황 공유",
    authorName: "최싸피",
    decidedAt: "2026-07-25T11:00:00",
  },
];
