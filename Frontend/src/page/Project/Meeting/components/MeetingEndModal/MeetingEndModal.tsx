import { useCallback, useEffect, useState, type FormEvent } from "react";
import style from "./MeetingEndModal.module.css";
import type { MeetingOutputOptions } from "../../api/meetingApi";

interface MeetingEndModalProps {
  isOpen: boolean;
  pending: boolean;
  onClose: () => void;
  onEnd: (options: MeetingOutputOptions) => void;
}

export default function MeetingEndModal({
  isOpen,
  pending,
  onClose,
  onEnd,
}: MeetingEndModalProps) {
  const [generateSummary, setGenerateSummary] = useState(false);
  const [generateNodes, setGenerateNodes] = useState(false);

  const handleClose = useCallback(() => {
    if (pending) return;

    setGenerateSummary(false);
    setGenerateNodes(false);
    onClose();
  }, [pending, onClose]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handleClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, handleClose]);

  if (!isOpen) {
    return null;
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (pending) return;

    onEnd({
      generateSummary,
      generateNodes,
    });
  };

  return (
    <div className={style.overlay} role="presentation" onClick={handleClose}>
      <section
        className={style.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="meeting-end-title"
        onClick={(event) => event.stopPropagation()}
      >
        <form onSubmit={handleSubmit}>
          <div className={style.header}>
            <div className={style.icon} aria-hidden="true">
              ✓
            </div>

            <h2 className={style.title} id="meeting-end-title">
              회의를 종료하시겠습니까?
            </h2>

            <p className={style.description}>
              필요한 AI 산출물을 선택하면 회의 종료 후 생성됩니다.
            </p>
          </div>

          <div className={style.options}>
            <label className={style.option}>
              <input
                className={style.checkbox}
                type="checkbox"
                checked={generateSummary}
                disabled={pending}
                onChange={(event) => setGenerateSummary(event.target.checked)}
              />

              <span>
                <strong className={style.optionTitle}>회의록 생성</strong>
                <span className={style.optionDescription}>
                  회의 내용을 정리하여 AI 회의 요약을 생성합니다.
                </span>
              </span>
            </label>

            <label className={style.option}>
              <input
                className={style.checkbox}
                type="checkbox"
                checked={generateNodes}
                disabled={pending}
                onChange={(event) => setGenerateNodes(event.target.checked)}
              />

              <span>
                <strong className={style.optionTitle}>노드 생성</strong>
                <span className={style.optionDescription}>
                  회의에서 논의된 내용을 바탕으로 노드를 생성합니다.
                </span>
              </span>
            </label>
          </div>

          <div className={style.footer}>
            <button
              className={style.cancelButton}
              type="button"
              disabled={pending}
              onClick={handleClose}
            >
              취소
            </button>

            <button
              className={style.endButton}
              type="submit"
              disabled={pending}
            >
              {pending ? "종료 중…" : "종료"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
