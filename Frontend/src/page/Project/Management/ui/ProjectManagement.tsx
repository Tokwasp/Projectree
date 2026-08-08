import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuthStore } from "../../../../store/authStore";
import useProjectList from "../../List/hooks/useProjectList";
import useProjectMembers from "../../Member/hooks/useProjectMembers";
import ProjectDeleteModal from "../components/ProjectDeleteModal/ProjectDeleteModal";
import useDeleteProject from "../hooks/useDeleteProject";
import useLeaveProject from "../hooks/useLeaveProject";
import style from "../css/ProjectManagement.module.css";

export default function ProjectManagement() {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const parsedProjectId = Number(projectId);
  const validProjectId =
    Number.isInteger(parsedProjectId) && parsedProjectId > 0
      ? parsedProjectId
      : null;
  const memberId = useAuthStore((state) => state.memberId);
  const { projects, isLoading: isProjectLoading } = useProjectList(0, 100);
  const { members, isLoading: isMemberLoading } =
    useProjectMembers(validProjectId);
  const {
    deleteProject,
    isDeleting,
    error: deleteError,
    clearError,
  } = useDeleteProject();
  const {
    leaveProject,
    isLeaving,
    error: leaveError,
    clearError: clearLeaveError,
  } = useLeaveProject();

  const currentProject = projects.find(
    (project) => project.projectId === validProjectId,
  );
  const owner = members.find((member) => member.role === "OWNER");
  const currentMember = members.find(
    (member) => member.memberId === memberId,
  );
  const isOwner = currentMember?.role === "OWNER";
  const isProcessing = isDeleting || isLeaving;
  const actionError = isOwner ? deleteError : leaveError;
  const projectInitial = currentProject?.title.trim().charAt(0) || "P";
  const projectActionLabel = isMemberLoading
    ? "권한 확인 중..."
    : isOwner
      ? "프로젝트 삭제"
      : currentMember
        ? "프로젝트 나가기"
        : "권한을 확인할 수 없습니다";

  const handleOpenDeleteModal = () => {
    clearError();
    clearLeaveError();
    setIsDeleteModalOpen(true);
  };

  const handleCloseDeleteModal = () => {
    if (!isProcessing) {
      setIsDeleteModalOpen(false);
      clearError();
      clearLeaveError();
    }
  };

  const handleProjectAction = async () => {
    if (validProjectId === null || !currentMember) {
      return;
    }

    const isCompleted = isOwner
      ? await deleteProject(validProjectId)
      : await leaveProject(validProjectId);

    if (isCompleted) {
      navigate("/projects", { replace: true });
    }
  };

  return (
    <section className={style.page}>
      <header className={style.pageHeader}>
        <h1 className={style.title}>프로젝트 설정</h1>
        <p className={style.description}>
          프로젝트 정보와 참여 상태를 관리할 수 있습니다.
        </p>
      </header>

      <div className={style.contentGrid}>
        <section className={style.card}>
          <div className={style.cardHeader}>
            <h2 className={style.cardTitle}>일반 설정</h2>
            <p className={style.cardDescription}>
              프로젝트의 대표 정보입니다.
            </p>
          </div>

          <div className={style.settingList}>
            <div className={style.photoSetting}>
              <div>
                <h3 className={style.settingLabel}>프로젝트 사진</h3>
                <p className={style.settingDescription}>
                  프로젝트를 구분할 수 있는 대표 이미지입니다.
                </p>
              </div>

              <div className={style.photoControl}>
                <div className={style.projectImage} aria-hidden="true">
                  {currentProject?.thumbnailUrl ? (
                    <img
                      src={currentProject.thumbnailUrl}
                      alt=""
                    />
                  ) : (
                    projectInitial
                  )}
                </div>
                <button className={style.secondaryButton} type="button" disabled>
                  사진 변경
                </button>
              </div>
            </div>

            <div className={style.settingItem}>
              <div>
                <h3 className={style.settingLabel}>프로젝트 이름</h3>
                <p className={style.settingDescription}>
                  프로젝트에 표시되는 이름입니다.
                </p>
              </div>

              <div className={style.settingControl}>
                <span className={style.settingValue}>
                  {isProjectLoading
                    ? "불러오는 중..."
                    : (currentProject?.title ?? "-")}
                </span>
                <button className={style.secondaryButton} type="button" disabled>
                  변경
                </button>
              </div>
            </div>

            <div className={style.settingItem}>
              <div>
                <h3 className={style.settingLabel}>프로젝트 설명</h3>
                <p className={style.settingDescription}>
                  프로젝트의 목표와 내용을 소개합니다.
                </p>
              </div>

              <div className={style.settingControl}>
                <span className={style.settingValue}>-</span>
                <button className={style.secondaryButton} type="button" disabled>
                  변경
                </button>
              </div>
            </div>
          </div>
        </section>

        <aside className={style.sideColumn}>
          <section className={style.card}>
            <div className={style.cardHeader}>
              <h2 className={style.cardTitle}>프로젝트 정보</h2>
            </div>

            <dl className={style.infoList}>
              <div className={style.infoItem}>
                <dt>소유자</dt>
                <dd>
                  {isMemberLoading ? "불러오는 중..." : (owner?.name ?? "-")}
                </dd>
              </div>
              <div className={style.infoItem}>
                <dt>생성일</dt>
                <dd>-</dd>
              </div>
              <div className={style.infoItem}>
                <dt>멤버 수</dt>
                <dd>
                  {isProjectLoading
                    ? "불러오는 중..."
                    : currentProject
                      ? `${currentProject.memberCount}명`
                      : "-"}
                </dd>
              </div>
            </dl>
          </section>

          <section className={`${style.card} ${style.dangerCard}`}>
            <div className={style.cardHeader}>
              <h2 className={style.cardTitle}>프로젝트 관리</h2>
              <p className={style.cardDescription}>
                {isOwner
                  ? "프로젝트를 삭제하면 모든 데이터가 함께 삭제됩니다."
                  : "프로젝트를 나가면 더 이상 접근할 수 없습니다."}
              </p>
            </div>

            <button
              className={style.dangerButton}
              type="button"
              disabled={isMemberLoading || !currentMember}
              onClick={handleOpenDeleteModal}
            >
              {projectActionLabel}
            </button>
          </section>
        </aside>
      </div>

      <ProjectDeleteModal
        isOpen={isDeleteModalOpen}
        projectName={currentProject?.title ?? "현재"}
        actionType={isOwner ? "delete" : "leave"}
        isProcessing={isProcessing}
        error={actionError}
        onClose={handleCloseDeleteModal}
        onConfirm={() => void handleProjectAction()}
      />
    </section>
  );
}
