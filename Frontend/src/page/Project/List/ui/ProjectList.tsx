import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ProjectGrid from "../../../../components/ProjectGrid/ProjectGrid";
import { mockProjects } from "../../../../mocks/ProjectMocks";
import style from "../css/ProjectList.module.css";

const PROJECTS_PER_PAGE = 8;

export default function ProjectList() {
  const navigate = useNavigate();
  const [searchKeyword, setSearchKeyword] = useState("");
  const [currentPage, setCurrentPage] = useState(1);

  const normalizedKeyword = searchKeyword.trim().toLowerCase();

  const filteredProjects = mockProjects.filter((project) =>
    project.title.toLowerCase().includes(normalizedKeyword),
  );

  const totalPages = Math.ceil(filteredProjects.length / PROJECTS_PER_PAGE);
  const startIndex = (currentPage - 1) * PROJECTS_PER_PAGE;
  const paginatedProjects = filteredProjects.slice(
    startIndex,
    startIndex + PROJECTS_PER_PAGE,
  );

  const pages = Array.from({ length: totalPages }, (_, index) => index + 1);

  const handleSearchChange = (value: string) => {
    setSearchKeyword(value);
    setCurrentPage(1);
  };

  return (
    <section className={style.section}>
      <h1 className={style.title}>프로젝트</h1>

      <div className={style.toolbar}>
        <input
          className={style.searchInput}
          type="search"
          value={searchKeyword}
          placeholder="프로젝트 검색..."
          aria-label="프로젝트 검색"
          onChange={(event) => handleSearchChange(event.target.value)}
        />

        <button
          className={style.createButton}
          type="button"
          onClick={() => navigate("/projects/create")}
        >
          프로젝트 만들기
        </button>
      </div>

      <ProjectGrid
        projects={paginatedProjects}
        emptyMessage="검색 결과가 없습니다."
      />

      {totalPages > 1 && (
        <nav className={style.pagination} aria-label="프로젝트 페이지">
          <button
            className={style.pageButton}
            type="button"
            disabled={currentPage === 1}
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
              aria-current={page === currentPage ? "page" : undefined}
              onClick={() => setCurrentPage(page)}
            >
              {page}
            </button>
          ))}

          <button
            className={style.pageButton}
            type="button"
            disabled={currentPage === totalPages}
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
