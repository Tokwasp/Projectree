import { Link } from "react-router-dom";
import ProjectGrid from "../../../../components/ProjectGrid/ProjectGrid";
import ProjectGridSkeleton from "../../../../components/ProjectGridSkeleton/ProjectGridSkeleton";
import type { ProjectSummary } from "../../../../types/Project";
import RecentProjectTitleIcon from "../../assets/recent_project_title_icon.png";
import style from "./RecentProjectSection.module.css";

interface RecentProjectSectionProps {
  projects: ProjectSummary[];
  isLoading: boolean;
}

export default function RecentProjectSection({
  projects,
  isLoading,
}: RecentProjectSectionProps) {
  return (
    <section className={style.section}>
      <div className={style.sectionHeader}>
        <h2 className={style.title}>
          <span className={style.titleIcon} aria-hidden="true">
            <img src={RecentProjectTitleIcon} alt="" />
          </span>
          최근 프로젝트
        </h2>

        <Link className={style.viewAllButton} to="/projects">
          전체 프로젝트 보기
        </Link>
      </div>

      {isLoading ? (
        <ProjectGridSkeleton count={4} variant="compact" />
      ) : (
        <ProjectGrid
          projects={projects}
          emptyMessage="참여 중인 프로젝트가 없습니다."
          variant="compact"
        />
      )}
    </section>
  );
}
