import ProfileSection from "../components/ProfileSection/ProfileSection";
import MyProjectList from "../components/MyProjectList/MyProjectList";
import useProjectList from "../../Project/List/hooks/useProjectList";
import { mockUserProfile } from "../../../mocks/MyPageMocks";
import style from "../css/MyPage.module.css";

const MY_PROJECT_LIST_SIZE = 4;

export default function MyPage() {
  const { projects, isLoading, error } = useProjectList(
    0,
    MY_PROJECT_LIST_SIZE,
  );

  return (
    <div className={style.page}>
      <ProfileSection user={mockUserProfile} />

      {isLoading && projects.length === 0 ? (
        <p>프로젝트 목록을 불러오는 중입니다.</p>
      ) : error ? (
        <p role="alert">{error}</p>
      ) : (
        <MyProjectList projects={projects} />
      )}

      <div className={style.accountActions}>
        <button className={style.logoutButton} type="button">
          로그아웃
        </button>

        <button className={style.deleteButton} type="button">
          계정 삭제
        </button>
      </div>
    </div>
  );
}
