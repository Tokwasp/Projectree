import { useNavigate, useParams } from "react-router-dom";
import type { InvitationStatus } from "../api/invitationApi";
import useInvitationLanding from "../hooks/useInvitationLanding";
import style from "../css/InvitationLanding.module.css";

function getStatusMessage(
  status: InvitationStatus,
  expired: boolean,
) {
  if (expired) {
    return "만료된 초대입니다.";
  }

  switch (status) {
    case "ACCEPTED":
      return "이미 수락한 초대입니다.";
    case "REJECTED":
      return "이미 거절한 초대입니다.";
    case "CANCELED":
      return "취소된 초대입니다.";
    default:
      return null;
  }
}

export default function InvitationLanding() {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  const {
    invitation,
    isLoading,
    isAccepting,
    isRejecting,
    error,
    acceptInvitation,
    rejectInvitation,
  } = useInvitationLanding(token ?? null);

  const handleAccept = async () => {
    const projectId = await acceptInvitation();

    if (projectId !== null) {
      navigate(`/projects/${projectId}`);
    }
  };

  const handleReject = async () => {
    await rejectInvitation();
  };

  if (isLoading) {
    return (
      <main className={style.page}>
        <div className={style.card}>초대 정보를 불러오는 중입니다.</div>
      </main>
    );
  }

  if (error || !invitation) {
    return (
      <main className={style.page}>
        <div className={style.card}>
          <h1 className={style.title}>초대를 확인할 수 없습니다.</h1>
          <p className={style.message} role="alert">
            {error ?? "유효하지 않은 초대입니다."}
          </p>
          <button
            className={style.secondaryButton}
            type="button"
            onClick={() => navigate("/home")}
          >
            홈으로 이동
          </button>
        </div>
      </main>
    );
  }

  const statusMessage = getStatusMessage(
    invitation.status,
    invitation.expired,
  );
  const canAccept =
    invitation.status === "PENDING" && !invitation.expired;

  return (
    <main className={style.page}>
      <div className={style.card}>
        <span className={style.eyebrow}>프로젝트 초대</span>

        <h1 className={style.title}>{invitation.projectTitle}</h1>

        <p className={style.message}>
          <strong>{invitation.inviterName}</strong>님이 프로젝트에
          초대했습니다.
        </p>

        {statusMessage && (
          <p className={style.statusMessage}>{statusMessage}</p>
        )}

        <div className={style.actions}>
          {canAccept && (
            <button
              className={style.primaryButton}
              type="button"
              disabled={isAccepting || isRejecting}
              onClick={() => void handleAccept()}
            >
              {isAccepting ? "수락 중..." : "초대 수락"}
            </button>
          )}

          {canAccept && (
            <button
              className={style.rejectButton}
              type="button"
              disabled={isAccepting || isRejecting}
              onClick={() => void handleReject()}
            >
              {isRejecting ? "거절 중..." : "초대 거절"}
            </button>
          )}

          <button
            className={style.secondaryButton}
            type="button"
            onClick={() => navigate("/home")}
          >
            홈으로 이동
          </button>
        </div>
      </div>
    </main>
  );
}
