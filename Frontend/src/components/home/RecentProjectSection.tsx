import { Link } from "react-router-dom";
import ProjectGrid from "../project/ProjectGrid";
import type { ProjectSummary } from "../../types/Project";
import style from "../../css/components/home/RecentProjectSection.module.css";

interface RecentProjectSectionProps {
  projects: ProjectSummary[];
}

export default function RecentProjectSection({
  projects,
}: RecentProjectSectionProps) {
  return (
    <section className={style.section}>
      <div className={style.sectionHeader}>
        <h1 className={style.title}>최근 프로젝트</h1>

        <Link className={style.viewAllButton} to="/projects">
          전체 프로젝트 보기
        </Link>
      </div>

      <ProjectGrid
        projects={projects}
        emptyMessage="참여 중인 프로젝트가 없습니다."
      />
    </section>
  );
}
