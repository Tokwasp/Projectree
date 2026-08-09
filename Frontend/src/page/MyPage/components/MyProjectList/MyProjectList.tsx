import { Link } from "react-router-dom";
import type { ProjectSummary } from "../../../../types/Project";
import MyProjectListSkeleton from "./MyProjectListSkeleton";
import style from "./MyProjectList.module.css";

interface MyProjectListProps {
  projects: ProjectSummary[];
  isLoading: boolean;
}

export default function MyProjectList({
  projects,
  isLoading,
}: MyProjectListProps) {
  return (
    <section className={style.section}>
      <div className={style.sectionHeader}>
        <h2 className={style.title}>
          참여 중인 프로젝트
        </h2>

        <Link className={style.viewAllLink} to="/projects">
          전체 프로젝트 보기
        </Link>
      </div>

      {isLoading ? (
        <MyProjectListSkeleton />
      ) : projects.length === 0 ? (
        <p className={style.emptyMessage}>
          참여 중인 프로젝트가 없습니다.
        </p>
      ) : (
        <div className={style.projectCard}>
          <ul className={style.projectList}>
            {projects.map((project) => (
              <li key={project.projectId}>
                <Link
                  className={style.projectRow}
                  to={`/projects/${project.projectId}`}
                  aria-label={`${project.title} 프로젝트로 이동`}
                >
                  <span className={style.projectInfo}>
                    {project.thumbnailUrl ? (
                      <img
                        className={style.projectThumbnail}
                        src={project.thumbnailUrl}
                        alt=""
                      />
                    ) : (
                      <span
                        className={style.projectFallback}
                        aria-hidden="true"
                      >
                        {project.title.charAt(0)}
                      </span>
                    )}

                    <span className={style.projectCopy}>
                      <span className={style.projectName}>
                        {project.title}
                      </span>
                      <span className={style.memberCount}>
                        참여 인원 {project.memberCount}명
                      </span>
                    </span>
                  </span>

                  <span className={style.arrow} aria-hidden="true">
                    ›
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
