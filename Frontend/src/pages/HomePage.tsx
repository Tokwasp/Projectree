import RecentProjectSection from "../components/home/RecentProjectSection";
import type { ProjectSummary } from "../types/Project";

const mockProjects: ProjectSummary[] = [
  {
    projectId: 1,
    title: "Projectree 서비스 구축",
    ownerName: "김싸피",
    memberCount: 6,
    createdAt: "2026-07-15T10:00:00",
  },
  {
    projectId: 2,
    title: "AI 협업 플랫폼 개발",
    ownerName: "이싸피",
    memberCount: 5,
    createdAt: "2026-07-16T09:30:00",
  },
  {
    projectId: 3,
    title: "실시간 화상 회의 서비스",
    ownerName: "박싸피",
    memberCount: 4,
    createdAt: "2026-07-17T14:00:00",
  },
  {
    projectId: 4,
    title: "지식 그래프 PoC",
    ownerName: "최싸피",
    memberCount: 6,
    createdAt: "2026-07-18T11:20:00",
  },
  {
    projectId: 5,
    title: "팀 일정 관리 시스템",
    ownerName: "정싸피",
    memberCount: 5,
    createdAt: "2026-07-19T09:00:00",
  },
  {
    projectId: 6,
    title: "회의 아카이빙 플랫폼",
    ownerName: "한싸피",
    memberCount: 4,
    createdAt: "2026-07-20T13:30:00",
  },
  {
    projectId: 7,
    title: "프로젝트 UX 개선",
    ownerName: "윤싸피",
    memberCount: 6,
    createdAt: "2026-07-21T10:40:00",
  },
  {
    projectId: 8,
    title: "통합 API 관리 프로젝트",
    ownerName: "장싸피",
    memberCount: 5,
    createdAt: "2026-07-22T15:10:00",
  },
];

export default function HomePage() {
  return <RecentProjectSection projects={mockProjects} />;
}
