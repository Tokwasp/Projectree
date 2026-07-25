import style from "../../css/components/project/ProjectPagination.module.css";

interface ProjectPaginationProps {
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export default function ProjectPagination({
  currentPage,
  totalPages,
  onPageChange,
}: ProjectPaginationProps) {
  if (totalPages <= 1) {
    return null;
  }

  const pages = Array.from({ length: totalPages }, (_, index) => index + 1);

  return (
    <nav className={style.pagination} aria-label="프로젝트 페이지">
      <button
        className={style.pageButton}
        type="button"
        disabled={currentPage === 1}
        aria-label="이전 페이지"
        onClick={() => onPageChange(currentPage - 1)}
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
          onClick={() => onPageChange(page)}
        >
          {page}
        </button>
      ))}

      <button
        className={style.pageButton}
        type="button"
        disabled={currentPage === totalPages}
        aria-label="다음 페이지"
        onClick={() => onPageChange(currentPage + 1)}
      >
        ›
      </button>
    </nav>
  );
}