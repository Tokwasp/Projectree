import useLogout from "../../Auth/hooks/useLogout";
import ProfileSection from "../components/ProfileSection/ProfileSection";
import MyProjectList from "../components/MyProjectList/MyProjectList";
import useProjectList from "../../Project/List/hooks/useProjectList";
import useMemberProfile from "../hooks/useMemberProfile";
import style from "../css/MyPage.module.css";

const MY_PROJECT_LIST_SIZE = 100;

export default function MyPage() {
  const {
    logout,
    isLoggingOut,
    error: logoutError,
  } = useLogout();
  const {
    profile,
    isLoading: isProfileLoading,
    error: profileError,
  } = useMemberProfile();
  const { projects, isLoading, error: projectError } = useProjectList(
    0,
    MY_PROJECT_LIST_SIZE,
  );

  return (
    <div className={style.page}>
      <header className={style.heading}>
        <h1 className={style.title}>마이페이지</h1>
        <p className={style.description}>
          프로필과 계정 정보를 관리하세요.
        </p>
      </header>

      {isProfileLoading ? (
        <p>회원 정보를 불러오는 중입니다.</p>
      ) : profileError ? (
        <p role="alert">{profileError}</p>
      ) : profile ? (
        <ProfileSection
          name={profile.name}
          email={profile.email}
          profileImageUrl={profile.profileImageUrl}
        />
      ) : null}

      {isLoading && projects.length === 0 ? (
        <p>프로젝트 목록을 불러오는 중입니다.</p>
      ) : projectError ? (
        <p role="alert">{projectError}</p>
      ) : (
        <MyProjectList projects={projects} />
      )}

      <div className={style.accountActions}>
        <button
          className={style.logoutButton}
          type="button"
          disabled={isLoggingOut}
          onClick={() => void logout()}
        >
          {isLoggingOut ? "로그아웃 중..." : "로그아웃"}
        </button>

        <button className={style.deleteButton} type="button">
          계정 삭제
        </button>

        {logoutError && (
          <p className={style.logoutError} role="alert">
            {logoutError}
          </p>
        )}
      </div>
    </div>
  );
}
