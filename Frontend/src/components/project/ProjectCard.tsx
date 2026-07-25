import type { ProjectSummary } from "../../types/Project";
import style from "../../css/project/ProjectCard.module.css";

interface ProjectCardProps {
  project: ProjectSummary;
}

export default function ProjectCard({ project }: ProjectCardProps) {
  return (
    <article className={style.card}>
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

        <button
          className={style.menuButton}
          type="button"
          aria-label={`${project.title} 메뉴 열기`}
        >
          ⋮
        </button>
      </div>

      <div className={style.cardContent}>
        <h3 className={style.projectName}>{project.title}</h3>

        <div className={style.projectMeta}>
          <span>팀원 {project.memberCount}명</span>
        </div>
      </div>
    </article>
  );
}
