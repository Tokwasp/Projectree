import { useEffect } from "react";
import style from "./ProjectDeleteModal.module.css";

interface ProjectDeleteModalProps {
  isOpen: boolean;
  projectName: string;
  actionType: "delete" | "leave";
  isProcessing: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}

export default function ProjectDeleteModal({
  isOpen,
  projectName,
  actionType,
  isProcessing,
  error,
  onClose,
  onConfirm,
}: ProjectDeleteModalProps) {
  useEffect(() => {
    if (!isOpen || isProcessing) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, isProcessing, onClose]);

  if (!isOpen) {
    return null;
  }

  const handleOverlayClick = () => {
    if (!isProcessing) {
      onClose();
    }
  };

  const isDeleteAction = actionType === "delete";

  return (
    <div
      className={style.overlay}
      role="presentation"
      onClick={handleOverlayClick}
    >
      <section
        className={style.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-delete-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className={style.header}>
          <div className={style.icon} aria-hidden="true">
            !
          </div>
          <h2 className={style.title} id="project-delete-title">
            {isDeleteAction
              ? "프로젝트를 삭제하시겠습니까?"
              : "프로젝트에서 나가시겠습니까?"}
          </h2>
          <p className={style.description}>
            {isDeleteAction ? (
              <>
                <strong>{projectName}</strong> 프로젝트와 관련된 데이터가
                모두 삭제되며, 삭제 후에는 복구할 수 없습니다.
              </>
            ) : (
              <>
                <strong>{projectName}</strong> 프로젝트에서 나가면 더 이상
                프로젝트에 접근할 수 없습니다.
              </>
            )}
          </p>
        </div>

        {error && (
          <p className={style.error} role="alert">
            {error}
          </p>
        )}

        <div className={style.footer}>
          <button
            className={style.cancelButton}
            type="button"
            disabled={isProcessing}
            onClick={onClose}
          >
            취소
          </button>
          <button
            className={style.confirmButton}
            type="button"
            disabled={isProcessing}
            onClick={onConfirm}
          >
            {isProcessing
              ? isDeleteAction
                ? "삭제 중..."
                : "나가는 중..."
              : isDeleteAction
                ? "삭제"
                : "나가기"}
          </button>
        </div>
      </section>
    </div>
  );
}
