import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import NotificationMenu from "../NotificationMenu/NotificationMenu";
import style from "./AppHeader.module.css";

interface AppHeaderProps {
  startContent?: ReactNode;
}

export default function AppHeader({ startContent }: AppHeaderProps) {
  const navigate = useNavigate();
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const name = useAuthStore((state) => state.name);
  const imageUrl = useAuthStore((state) => state.imageUrl);
  const logout = useAuthStore((state) => state.logout);

  const handleLogout = () => {
    logout();
    navigate("/", { replace: true });
  };

  return (
    <div className={style.container}>
      {startContent && (
        <div className={style.startContent}>{startContent}</div>
      )}

      <div className={style.searchArea}>
        <input
          className={style.searchInput}
          type="search"
          placeholder="프로젝트 검색..."
          aria-label="프로젝트 검색"
        />
      </div>

      <div className={style.actions}>
        <NotificationMenu />

        <div
          className={style.profileMenuWrapper}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) {
              setIsProfileMenuOpen(false);
            }
          }}
        >
          <button
            className={style.profileButton}
            type="button"
            aria-label="사용자 메뉴 열기"
            aria-expanded={isProfileMenuOpen}
            aria-controls="profile-menu"
            onClick={() => setIsProfileMenuOpen((current) => !current)}
          >
            {imageUrl ? (
              <img className={style.profileImage} src={imageUrl} alt="" />
            ) : (
              <span className={style.profileFallback} aria-hidden="true">
                {name?.charAt(0) ?? "P"}
              </span>
            )}
          </button>

          {isProfileMenuOpen && (
            <div className={style.profileMenu} id="profile-menu">
              <Link
                className={style.profileMenuItem}
                to="/mypage"
                onClick={() => setIsProfileMenuOpen(false)}
              >
                마이페이지
              </Link>
              <button
                className={`${style.profileMenuItem} ${style.logoutButton}`}
                type="button"
                onClick={handleLogout}
              >
                로그아웃
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
