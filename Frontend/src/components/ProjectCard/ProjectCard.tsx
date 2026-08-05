import { useState } from "react";
import { Link } from "react-router-dom";
import type { ProjectSummary } from "../../types/Project";
import style from "./ProjectCard.module.css";

interface ProjectCardProps {
  project: ProjectSummary;
  variant?: "default" | "compact";
}

export default function ProjectCard({
  project,
  variant = "default",
}: ProjectCardProps) {
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const menuId = `project-card-menu-${project.projectId}`;

  return (
    <article
      className={`${style.card} ${variant === "compact" ? style.cardCompact : ""}`}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setIsMenuOpen(false);
        }
      }}
    >
      <Link
        className={style.cardLink}
        to={`/projects/${project.projectId}`}
        aria-label={`${project.title} 프로젝트로 이동`}
      >
        <div className={style.projectVisual}>
          {project.thumbnailUrl ? (
            <img
              className={style.projectThumbnail}
              src={project.thumbnailUrl}
              alt=""
            />
          ) : (
            <span className={style.projectFallback} aria-hidden="true">
              {project.title.charAt(0)}
            </span>
          )}
        </div>

        <div className={style.cardContent}>
          <h3 className={style.projectName}>{project.title}</h3>

          <div className={style.projectMeta}>
            <span>참여 인원 {project.memberCount}명</span>
          </div>
        </div>
      </Link>

      <button
        className={style.menuButton}
        type="button"
        aria-label={`${project.title} 메뉴 열기`}
        aria-expanded={isMenuOpen}
        aria-controls={menuId}
        onClick={() => setIsMenuOpen((current) => !current)}
      >
        ⋮
      </button>

      {isMenuOpen && (
        <div className={style.cardMenu} id={menuId}>
          <button className={style.deleteButton} type="button">
            프로젝트 삭제
          </button>
        </div>
      )}
    </article>
  );
}
