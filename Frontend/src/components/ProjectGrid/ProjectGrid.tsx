import ProjectCard from "../ProjectCard/ProjectCard";
import type { ProjectSummary } from "../../types/Project";
import style from "./ProjectGrid.module.css";

interface ProjectGridProps {
  projects: ProjectSummary[];
  emptyMessage: string;
  variant?: "default" | "compact";
}

export default function ProjectGrid({
  projects,
  emptyMessage,
  variant = "default",
}: ProjectGridProps) {
  if (projects.length === 0) {
    return <p className={style.emptyMessage}>{emptyMessage}</p>;
  }

  return (
    <div
      className={`${style.projectGrid} ${variant === "compact" ? style.projectGridCompact : ""}`}
    >
      {projects.map((project) => (
        <ProjectCard
          key={project.projectId}
          project={project}
          variant={variant}
        />
      ))}
    </div>
  );
}
