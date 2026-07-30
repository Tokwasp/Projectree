import style from "./ProjectToolbar.module.css";

interface ProjectToolbarProps {
  searchKeyword: string;
  onSearchChange: (value: string) => void;
  onCreateClick: () => void;
}

export default function ProjectToolbar({
  searchKeyword,
  onSearchChange,
  onCreateClick,
}: ProjectToolbarProps) {
  return (
    <div className={style.toolbar}>
      <input
        className={style.searchInput}
        type="search"
        value={searchKeyword}
        placeholder="프로젝트 검색..."
        aria-label="프로젝트 검색"
        onChange={(event) => onSearchChange(event.target.value)}
      />

      <button
        className={style.createButton}
        type="button"
        onClick={onCreateClick}
      >
        프로젝트 만들기
      </button>
    </div>
  );
}
