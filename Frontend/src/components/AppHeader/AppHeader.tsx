import { Link } from "react-router-dom";
import NotificationIcon from "../../assets/icons/header/notification.png";
import { useAuthStore } from "../../store/authStore";
import style from "./AppHeader.module.css";

export default function AppHeader() {
  const name = useAuthStore((state) => state.name);
  const imageUrl = useAuthStore((state) => state.imageUrl);

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
          <img
            className={style.notificationIcon}
            src={NotificationIcon}
            alt=""
            aria-hidden="true"
          />
        </button>

        <Link
          className={style.profileLink}
          to="/mypage"
          aria-label="마이페이지로 이동"
        >
          {imageUrl ? (
            <img className={style.profileImage} src={imageUrl} alt="" />
          ) : (
            <span className={style.profileFallback} aria-hidden="true">
              {name?.charAt(0) ?? "P"}
            </span>
          )}
        </Link>
      </div>
    </div>
  );
}
