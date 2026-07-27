import ProjectGrid from "./ProjectGrid";
import ProjectPagination from "./ProjectPagination";
import ProjectToolbar from "./ProjectToolbar";
import type { ProjectSummary } from "../../types/Project";
import style from "../../css/project/ProjectListSection.module.css";

interface ProjectListSectionProps {
  projects: ProjectSummary[];
  searchKeyword: string;
  currentPage: number;
  totalPages: number;
  onSearchChange: (value: string) => void;
  onPageChange: (page: number) => void;
  onCreateClick: () => void;
}

export default function ProjectListSection({
  projects,
  searchKeyword,
  currentPage,
  totalPages,
  onSearchChange,
  onPageChange,
  onCreateClick,
}: ProjectListSectionProps) {
  return (
    <section className={style.section}>
      <h1 className={style.title}>프로젝트</h1>

      <ProjectToolbar
        searchKeyword={searchKeyword}
        onSearchChange={onSearchChange}
        onCreateClick={onCreateClick}
      />

      <ProjectGrid
        projects={projects}
        emptyMessage="검색 결과가 없습니다."
      />

      <ProjectPagination
        currentPage={currentPage}
        totalPages={totalPages}
        onPageChange={onPageChange}
      />
    </section>
  );
}
