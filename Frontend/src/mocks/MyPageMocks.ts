import projectPlaceholder from "../assets/project-placeholder.svg";
import type {
  UserProfile,
  UserProjectSummary,
} from "../types/User";

export const mockUserProfile: UserProfile = {
  userId: 1,
  name: "김싸피",
  email: "ssafy@example.com",
};

export const mockUserProjects: UserProjectSummary[] = [
  {
    projectId: 1,
    title: "Projectree 서비스 구축",
    role: "프로젝트 관리자",
    joinedAt: "2026-07-15T10:00:00",
    lastActivityAt: "2026-07-24T14:00:00",
    thumbnailUrl: projectPlaceholder,
  },
  {
    projectId: 2,
    title: "AI 협업 플랫폼 개발",
    role: "팀 리더",
    joinedAt: "2026-07-16T09:30:00",
    lastActivityAt: "2026-07-23T16:30:00",
    thumbnailUrl: projectPlaceholder,
  },
  {
    projectId: 3,
    title: "실시간 화상 회의 서비스",
    role: "팀원",
    joinedAt: "2026-07-17T14:00:00",
    lastActivityAt: "2026-07-22T11:20:00",
    thumbnailUrl: projectPlaceholder,
  },
  {
    projectId: 4,
    title: "지식 그래프 PoC",
    role: "팀원",
    joinedAt: "2026-07-18T11:20:00",
    lastActivityAt: "2026-07-21T15:10:00",
    thumbnailUrl: projectPlaceholder,
  },
];