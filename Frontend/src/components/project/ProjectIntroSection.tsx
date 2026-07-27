import type { ProjectHomeSummary } from "../../types/ProjectHome";
import style from "../../css/project/ProjectIntroSection.module.css";

interface ProjectIntroSectionProps {
  project: ProjectHomeSummary;
}

export default function ProjectIntroSection({
  project,
}: ProjectIntroSectionProps) {
  return (
    <section
      className={style.section}
      aria-labelledby="project-intro-heading"
    >
      <h1
        className={style.heading}
        id="project-intro-heading"
      >
        프로젝트 소개
      </h1>

      <h2 className={style.projectName}>{project.title}</h2>
      <p className={style.description}>{project.description}</p>
    </section>
  );
}