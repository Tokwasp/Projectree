import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ProjectGrid from "../../../../components/ProjectGrid/ProjectGrid";
import useProjectList from "../hooks/useProjectList";
import style from "../css/ProjectList.module.css";

const PROJECTS_PER_PAGE = 8;

export default function ProjectList() {
  const navigate = useNavigate();
  const [currentPage, setCurrentPage] = useState(0);
  const { projects, totalPages, isLoading, error } = useProjectList(
    currentPage,
    PROJECTS_PER_PAGE,
  );

  const pages = Array.from({ length: totalPages }, (_, index) => index);

  return (
    <section className={style.section}>
      <h1 className={style.title}>프로젝트</h1>

      <div className={style.toolbar}>
        <button
          className={style.createButton}
          type="button"
          onClick={() => navigate("/projects/create")}
        >
          프로젝트 만들기
        </button>
      </div>

      {isLoading && projects.length === 0 ? (
        <p>프로젝트 목록을 불러오는 중입니다.</p>
      ) : error ? (
        <p role="alert">{error}</p>
      ) : (
        <ProjectGrid
          projects={projects}
          emptyMessage="참여 중인 프로젝트가 없습니다."
        />
      )}

      {totalPages > 1 && (
        <nav className={style.pagination} aria-label="프로젝트 페이지">
          <button
            className={style.pageButton}
            type="button"
            disabled={currentPage === 0 || isLoading}
            aria-label="이전 페이지"
            onClick={() => setCurrentPage(currentPage - 1)}
          >
            ‹
          </button>

          {pages.map((page) => (
            <button
              className={`${style.pageButton} ${
                page === currentPage ? style.pageButtonActive : ""
              }`}
              type="button"
              key={page}
              disabled={isLoading}
              aria-current={page === currentPage ? "page" : undefined}
              onClick={() => setCurrentPage(page)}
            >
              {page + 1}
            </button>
          ))}

          <button
            className={style.pageButton}
            type="button"
            disabled={currentPage === totalPages - 1 || isLoading}
            aria-label="다음 페이지"
            onClick={() => setCurrentPage(currentPage + 1)}
          >
            ›
          </button>
        </nav>
      )}
    </section>
  );
}
