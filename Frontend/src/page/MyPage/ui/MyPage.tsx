import { useNavigate } from "react-router-dom";
import ProfileSection from "../components/ProfileSection/ProfileSection";
import MyProjectList from "../components/MyProjectList/MyProjectList";
import useProjectList from "../../Project/List/hooks/useProjectList";
import { useAuthStore } from "../../../store/authStore";
import style from "../css/MyPage.module.css";

const MY_PROJECT_LIST_SIZE = 100;

export default function MyPage() {
  const navigate = useNavigate();
  const name = useAuthStore((state) => state.name);
  const imageUrl = useAuthStore((state) => state.imageUrl);
  const logout = useAuthStore((state) => state.logout);
  const { projects, isLoading, error } = useProjectList(
    0,
    MY_PROJECT_LIST_SIZE,
  );

  const handleLogout = () => {
    logout();
    navigate("/", { replace: true });
  };

  return (
    <div className={style.page}>
      <header className={style.heading}>
        <h1 className={style.title}>마이페이지</h1>
        <p className={style.description}>
          프로필과 계정 정보를 관리하세요.
        </p>
      </header>

      <ProfileSection
        name={name ?? "사용자"}
        profileImageUrl={imageUrl}
      />

      {isLoading && projects.length === 0 ? (
        <p>프로젝트 목록을 불러오는 중입니다.</p>
      ) : error ? (
        <p role="alert">{error}</p>
      ) : (
        <MyProjectList projects={projects} />
      )}

      <div className={style.accountActions}>
        <button
          className={style.logoutButton}
          type="button"
          onClick={handleLogout}
        >
          로그아웃
        </button>

        <button className={style.deleteButton} type="button">
          계정 삭제
        </button>
      </div>
    </div>
  );
}
