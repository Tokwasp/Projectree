import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import useLogout from "../../page/Auth/hooks/useLogout";
import { useAuthStore } from "../../store/authStore";
import NotificationMenu from "../NotificationMenu/NotificationMenu";
import style from "./AppHeader.module.css";

interface AppHeaderProps {
  startContent?: ReactNode;
}

export default function AppHeader({ startContent }: AppHeaderProps) {
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const name = useAuthStore((state) => state.name);
  const imageUrl = useAuthStore((state) => state.imageUrl);
  const { logout, isLoggingOut, error } = useLogout();

  return (
    <div className={style.container}>
      {startContent && (
        <div className={style.startContent}>{startContent}</div>
      )}

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
                disabled={isLoggingOut}
                onClick={() => void logout()}
              >
                {isLoggingOut ? "로그아웃 중..." : "로그아웃"}
              </button>

              {error && (
                <p className={style.logoutError} role="alert">
                  {error}
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
