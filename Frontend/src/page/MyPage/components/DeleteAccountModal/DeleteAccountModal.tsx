import { useEffect } from "react";
import style from "./DeleteAccountModal.module.css";

interface DeleteAccountModalProps {
  isOpen: boolean;
  isDeleting: boolean;
  error: string | null;
  onClose: () => void;
  onConfirm: () => void;
}

export default function DeleteAccountModal({
  isOpen,
  isDeleting,
  error,
  onClose,
  onConfirm,
}: DeleteAccountModalProps) {
  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !isDeleting) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, isDeleting, onClose]);

  if (!isOpen) {
    return null;
  }

  return (
    <div
      className={style.overlay}
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !isDeleting) {
          onClose();
        }
      }}
    >
      <section
        className={style.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-account-title"
        aria-describedby="delete-account-description"
      >
        <div className={style.icon} aria-hidden="true">
          !
        </div>

        <h2 className={style.title} id="delete-account-title">
          정말 탈퇴하시겠어요?
        </h2>

        <p className={style.description} id="delete-account-description">
          탈퇴하면 계정과 관련된 정보를 다시 이용할 수 없습니다.
        </p>

        {error && (
          <p className={style.error} role="alert">
            {error}
          </p>
        )}

        <div className={style.actions}>
          <button
            className={style.cancelButton}
            type="button"
            disabled={isDeleting}
            onClick={onClose}
          >
            취소
          </button>

          <button
            className={style.confirmButton}
            type="button"
            disabled={isDeleting}
            onClick={onConfirm}
          >
            {isDeleting ? "탈퇴 처리 중..." : "회원 탈퇴"}
          </button>
        </div>
      </section>
    </div>
  );
}