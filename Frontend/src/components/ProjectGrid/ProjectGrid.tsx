import ProjectCard from "../ProjectCard/ProjectCard";
import type { ProjectSummary } from "../../types/Project";
import style from "./ProjectGrid.module.css";

interface ProjectGridProps {
  projects: ProjectSummary[];
  emptyMessage: string;
}

export default function ProjectGrid({
  projects,
  emptyMessage,
}: ProjectGridProps) {
  if (projects.length === 0) {
    return <p className={style.emptyMessage}>{emptyMessage}</p>;
  }

  return (
    <div className={style.projectGrid}>
      {projects.map((project) => (
        <ProjectCard key={project.projectId} project={project} />
      ))}
    </div>
  );
}
