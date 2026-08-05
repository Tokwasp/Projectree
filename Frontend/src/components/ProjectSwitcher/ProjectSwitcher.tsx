import { useState } from "react";
import { Link } from "react-router-dom";
import type { ProjectSummary } from "../../types/Project";
import style from "./ProjectSwitcher.module.css";

interface ProjectSwitcherProps {
  projects: ProjectSummary[];
  currentProjectId: number | null;
  currentProjectName: string;
}

export default function ProjectSwitcher({
  projects,
  currentProjectId,
  currentProjectName,
}: ProjectSwitcherProps) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div
      className={style.container}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setIsOpen(false);
        }
      }}
    >
      <button
        className={style.button}
        type="button"
        aria-expanded={isOpen}
        aria-controls="project-switcher-menu"
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className={style.copy}>
          <span className={style.label}>현재 프로젝트</span>
          <strong className={style.projectName}>{currentProjectName}</strong>
        </span>
        <span
          className={`${style.chevron} ${isOpen ? style.chevronOpen : ""}`}
          aria-hidden="true"
        />
      </button>

      {isOpen && (
        <div className={style.dropdown} id="project-switcher-menu">
          {projects.map((project) => (
            <Link
              className={`${style.dropdownItem} ${project.projectId === currentProjectId ? style.dropdownItemActive : ""}`}
              key={project.projectId}
              to={`/projects/${project.projectId}`}
              onClick={() => setIsOpen(false)}
            >
              {project.title}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
