import style from "../../css/components/common/AppHeader.module.css";

export default function AppHeader() {
  return (
    <div className={style.container}>
      <div className={style.searchArea}>
        <input
          className={style.searchInput}
          type="search"
          placeholder="프로젝트, 팀, 문서 검색..."
          aria-label="통합 검색"
        />
      </div>

      <div className={style.actions}>
        <button
          className={style.actionButton}
          type="button"
          aria-label="알림"
        >
          알림
        </button>

        <button className={style.actionButton} type="button">
          사용자
        </button>
      </div>
    </div>
  );
}