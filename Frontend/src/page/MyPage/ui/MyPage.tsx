import ProfileSection from "../components/ProfileSection/ProfileSection";
import MyProjectList from "../components/MyProjectList/MyProjectList";
import {
  mockUserProfile,
  mockUserProjects,
} from "../../../mocks/MyPageMocks";
import style from "../css/MyPage.module.css";

export default function MyPage() {
  return (
    <div className={style.page}>
      <ProfileSection user={mockUserProfile} />

      <MyProjectList projects={mockUserProjects} />

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
