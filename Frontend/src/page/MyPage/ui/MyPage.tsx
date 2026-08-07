import { useState } from "react";
import useLogout from "../../Auth/hooks/useLogout";
import ProfileSection from "../components/ProfileSection/ProfileSection";
import MyProjectList from "../components/MyProjectList/MyProjectList";
import DeleteAccountModal from "../components/DeleteAccountModal/DeleteAccountModal";
import useProjectList from "../../Project/List/hooks/useProjectList";
import useMemberProfile from "../hooks/useMemberProfile";
import useDeleteMember from "../hooks/useDeleteMember";
import style from "../css/MyPage.module.css";

const MY_PROJECT_LIST_SIZE = 100;

export default function MyPage() {
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
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
  const {
    deleteMember,
    isDeleting,
    error: deleteError,
    clearError: clearDeleteError,
  } = useDeleteMember();
  const { projects, isLoading, error: projectError } = useProjectList(
    0,
    MY_PROJECT_LIST_SIZE,
  );

  const openDeleteModal = () => {
    clearDeleteError();
    setIsDeleteModalOpen(true);
  };

  const closeDeleteModal = () => {
    clearDeleteError();
    setIsDeleteModalOpen(false);
  };

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

        <button
          className={style.deleteButton}
          type="button"
          onClick={openDeleteModal}
        >
          회원 탈퇴
        </button>

        {logoutError && (
          <p className={style.logoutError} role="alert">
            {logoutError}
          </p>
        )}
      </div>

      <DeleteAccountModal
        isOpen={isDeleteModalOpen}
        isDeleting={isDeleting}
        error={deleteError}
        onClose={closeDeleteModal}
        onConfirm={() => void deleteMember()}
      />
    </div>
  );
}
