import type { UserProjectSummary } from "../../../../types/User";
import style from "./MyProjectList.module.css";

interface MyProjectListProps {
  projects: UserProjectSummary[];
}

function formatDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

export default function MyProjectList({
  projects,
}: MyProjectListProps) {
  return (
    <section className={style.section}>
      <h2 className={style.title}>참여 중인 프로젝트</h2>

      {projects.length === 0 ? (
        <p className={style.emptyMessage}>
          참여 중인 프로젝트가 없습니다.
        </p>
      ) : (
        <div className={style.tableWrapper}>
          <table className={style.table}>
            <thead>
              <tr>
                <th>프로젝트 이름</th>
                <th>역할</th>
                <th>참여일</th>
                <th>최근 활동</th>
              </tr>
            </thead>

            <tbody>
              {projects.map((project) => (
                <tr key={project.projectId}>
                  <td>
                    <div className={style.projectInfo}>
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

                      <span className={style.projectName}>
                        {project.title}
                      </span>
                    </div>
                  </td>
                  <td>{project.role}</td>
                  <td>
                    <time dateTime={project.joinedAt}>
                      {formatDate(project.joinedAt)}
                    </time>
                  </td>
                  <td>
                    <time dateTime={project.lastActivityAt}>
                      {formatDate(project.lastActivityAt)}
                    </time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
