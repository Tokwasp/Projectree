import type {
  AiFeedbackSummary,
  ProjectHomeSummary,
  RecentMeetingSummary,
  SpeakingTimeSummary,
} from "../types/ProjectHome";

export const mockProjectHome: ProjectHomeSummary = {
  projectId: 1,
  title: "Projectree 서비스 구축",
  description:
    "프로젝트의 진행 상황과 주요 정보를 체계적으로 관리하고, 회의와 결정사항을 한눈에 확인할 수 있는 협업 프로젝트입니다.",
  createdAt: "2026-07-10T00:00:00",
  memberCount: 9,
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

export const mockAiFeedback: AiFeedbackSummary = {
  details: [
    { label: "말하기 속도", description: "안정적인 속도로 핵심 내용을 전달했어요." },
    { label: "목소리 톤", description: "명확하고 편안한 톤을 유지했어요." },
    { label: "총평", description: "질문과 의견 제시의 균형이 좋았어요." },
  ],
};

export const mockSpeakingTimes: SpeakingTimeSummary[] = [
  { memberId: 1, name: "나", percentage: 28, isCurrentUser: true },
  { memberId: 2, name: "최싸피", percentage: 18, isCurrentUser: false },
  { memberId: 3, name: "박싸피", percentage: 22, isCurrentUser: false },
  { memberId: 4, name: "이싸피", percentage: 12, isCurrentUser: false },
  { memberId: 5, name: "김싸피", percentage: 20, isCurrentUser: false },
];
