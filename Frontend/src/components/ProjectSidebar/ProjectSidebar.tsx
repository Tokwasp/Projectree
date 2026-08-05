import { NavLink, useParams } from "react-router-dom";
import useProjectMembers from "../../page/Project/Member/hooks/useProjectMembers";
import type { ProjectSummary } from "../../types/Project";
import ProjectSwitcher from "../ProjectSwitcher/ProjectSwitcher";
import style from "./ProjectSidebar.module.css";

interface ProjectSidebarProps {
  projects: ProjectSummary[];
  currentProjectId: number | null;
  currentProjectName: string;
}

export default function ProjectSidebar({
  projects,
  currentProjectId,
  currentProjectName,
}: ProjectSidebarProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const parsedProjectId = Number(projectId);
  const validProjectId = Number.isInteger(parsedProjectId)
    ? parsedProjectId
    : null;
  const { members } = useProjectMembers(validProjectId);
  const visibleMembers = members.slice(0, 4);
  const hiddenMemberCount = Math.max(members.length - visibleMembers.length, 0);

  const projectMenus = [
    { label: "프로젝트 홈", to: `/projects/${projectId}`, end: true },
    { label: "회의", to: `/projects/${projectId}/meeting` },
    { label: "노드" },
    { label: "팀원", to: `/projects/${projectId}/members` },
    { label: "설정" },
  ];

  return (
    <div className={style.container}>
      <ProjectSwitcher
        projects={projects}
        currentProjectId={currentProjectId}
        currentProjectName={currentProjectName}
      />

      <div className={style.memberSection}>
        <span className={style.memberLabel}>팀원 {members.length}명</span>
        <div className={style.memberList} aria-label={`팀원 ${members.length}명`}>
          {visibleMembers.map((member) => (
            <span
              className={style.memberAvatar}
              key={member.memberId}
              title={member.name}
            >
              {member.name.charAt(0)}
            </span>
          ))}
          {hiddenMemberCount > 0 && (
            <span className={style.memberMore}>+{hiddenMemberCount}</span>
          )}
        </div>
      </div>

      <nav className={style.projectNavigation} aria-label="프로젝트 메뉴">
        {projectMenus.map((menu) =>
          menu.to ? (
            <NavLink
              className={({ isActive }) =>
                `${style.projectMenuButton} ${isActive ? style.projectMenuButtonActive : ""}`
              }
              end={menu.end}
              key={menu.label}
              to={menu.to}
            >
              {menu.label}
            </NavLink>
          ) : (
            <button
              className={style.projectMenuButton}
              key={menu.label}
              type="button"
              disabled
            >
              {menu.label}
            </button>
          ),
        )}
      </nav>
    </div>
  );
}
