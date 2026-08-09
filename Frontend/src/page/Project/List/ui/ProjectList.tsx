import { useState } from "react";
import { useNavigate } from "react-router-dom";
import ProjectGrid from "../../../../components/ProjectGrid/ProjectGrid";
import ProjectGridSkeleton from "../../../../components/ProjectGridSkeleton/ProjectGridSkeleton";
import CreateProjectIcon from "../../../Home/assets/create_project_icon.png";
import useDebouncedValue from "../hooks/useDebouncedValue";
import useProjectList from "../hooks/useProjectList";
import style from "../css/ProjectList.module.css";

const PROJECTS_PER_PAGE = 12;
const SKELETON_CARD_COUNT = 8;

export default function ProjectList() {
  const navigate = useNavigate();
  const [currentPage, setCurrentPage] = useState(0);
  const [searchInput, setSearchInput] = useState("");
  const debouncedKeyword = useDebouncedValue(searchInput, 300);
  const { projects, totalElements, totalPages, isLoading, error } =
    useProjectList(
      currentPage,
      PROJECTS_PER_PAGE,
      debouncedKeyword,
    );

  const pages = Array.from({ length: totalPages }, (_, index) => index);

  return (
    <section className={style.section}>
      <div className={style.heading}>
        <h1 className={style.title}>프로젝트</h1>
        <p className={style.description}>
          {debouncedKeyword ? "검색된 프로젝트가 " : "참여 중인 프로젝트가 "}
          총 <strong className={style.projectCount}>{totalElements}</strong>개예요.
        </p>
      </div>

      <div className={style.toolbar}>
        <div className={style.searchArea}>
          <input
            className={style.searchInput}
            type="search"
            placeholder="프로젝트 검색..."
            aria-label="프로젝트 검색"
            value={searchInput}
            onChange={(event) => {
              setSearchInput(event.target.value);
              setCurrentPage(0);
            }}
          />
        </div>

        <button
          className={style.createButton}
          type="button"
          onClick={() => navigate("/projects/create")}
        >
          <span className={style.createIconBox} aria-hidden="true">
            <img
              className={style.createIcon}
              src={CreateProjectIcon}
              alt=""
            />
          </span>
          프로젝트 만들기
        </button>
      </div>

      {isLoading && projects.length === 0 ? (
        <ProjectGridSkeleton count={SKELETON_CARD_COUNT} />
      ) : error ? (
        <p role="alert">{error}</p>
      ) : (
        <ProjectGrid
          projects={projects}
          emptyMessage={
            debouncedKeyword
              ? "검색 결과가 없습니다."
              : "참여 중인 프로젝트가 없습니다."
          }
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
