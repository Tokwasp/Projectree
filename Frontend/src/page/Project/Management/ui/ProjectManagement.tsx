import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useAuthStore } from "../../../../store/authStore";
import useProjectHome from "../../Home/hooks/useProjectHome";
import useProjectList from "../../List/hooks/useProjectList";
import useProjectMembers from "../../Member/hooks/useProjectMembers";
import ProjectDeleteModal from "../components/ProjectDeleteModal/ProjectDeleteModal";
import ProjectGeneralSettings from "../components/ProjectGeneralSettings/ProjectGeneralSettings";
import ProjectManagementSkeleton from "../components/ProjectManagementSkeleton/ProjectManagementSkeleton";
import useDeleteProject from "../hooks/useDeleteProject";
import useLeaveProject from "../hooks/useLeaveProject";
import style from "../css/ProjectManagement.module.css";

function formatProjectDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

export default function ProjectManagement() {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [updatedTitle, setUpdatedTitle] = useState<string | null>(null);
  const parsedProjectId = Number(projectId);
  const validProjectId =
    Number.isInteger(parsedProjectId) && parsedProjectId > 0
      ? parsedProjectId
      : null;
  const memberId = useAuthStore((state) => state.memberId);
  const { projects, isLoading: isProjectLoading } = useProjectList(0, 100);
  const { data: projectHome, isLoading: isProjectHomeLoading } =
    useProjectHome(validProjectId);
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
  const projectDetail = projectHome?.projectDetail;
  const isOwner = currentMember?.role === "OWNER";
  const isProcessing = isDeleting || isLeaving;
  const actionError = isOwner ? deleteError : leaveError;
  const projectName =
    updatedTitle ?? projectDetail?.projectTitle ?? currentProject?.title;
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

  if (isProjectLoading || isProjectHomeLoading || isMemberLoading) {
    return <ProjectManagementSkeleton />;
  }

  return (
    <section className={style.page}>
      <header className={style.pageHeader}>
        <h1 className={style.title}>프로젝트 설정</h1>
        <p className={style.description}>
          프로젝트 정보와 참여 상태를 관리할 수 있습니다.
        </p>
      </header>

      <div className={style.contentGrid}>
        <ProjectGeneralSettings
          projectId={validProjectId}
          isOwner={isOwner}
          projectName={projectName}
          projectContent={projectDetail?.projectContent}
          projectImage={currentProject?.thumbnailUrl}
          isProjectLoading={isProjectLoading}
          isProjectHomeLoading={isProjectHomeLoading}
          onTitleUpdated={setUpdatedTitle}
        />

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
                <dd>
                  {isProjectHomeLoading
                    ? "불러오는 중..."
                    : projectDetail?.projectCreatedAt
                      ? formatProjectDate(projectDetail.projectCreatedAt)
                      : "-"}
                </dd>
              </div>
              <div className={style.infoItem}>
                <dt>멤버 수</dt>
                <dd>
                  {isProjectHomeLoading
                    ? "불러오는 중..."
                    : projectDetail
                      ? `${projectDetail.participantCount}명`
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
        projectName={projectName ?? "현재"}
        actionType={isOwner ? "delete" : "leave"}
        isProcessing={isProcessing}
        error={actionError}
        onClose={handleCloseDeleteModal}
        onConfirm={() => void handleProjectAction()}
      />
    </section>
  );
}
