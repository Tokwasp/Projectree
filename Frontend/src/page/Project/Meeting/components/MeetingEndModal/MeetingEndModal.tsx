import { useEffect, useState, type FormEvent } from "react";
import style from "./MeetingEndModal.module.css";

export interface MeetingOutputOptions {
  createSummary: boolean;
  createNodes: boolean;
}

interface MeetingEndModalProps {
  isOpen: boolean;
  onClose: () => void;
  onEnd: (options: MeetingOutputOptions) => void;
}

export default function MeetingEndModal({
  isOpen,
  onClose,
  onEnd,
}: MeetingEndModalProps) {
  const [createSummary, setCreateSummary] = useState(false);
  const [createNodes, setCreateNodes] = useState(false);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setCreateSummary(false);
        setCreateNodes(false);
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) {
    return null;
  }

  const handleClose = () => {
    setCreateSummary(false);
    setCreateNodes(false);
    onClose();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    onEnd({
      createSummary,
      createNodes,
    });

    setCreateSummary(false);
    setCreateNodes(false);
  };

  return (
    <div
      className={style.overlay}
      role="presentation"
      onClick={handleClose}
    >
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
                checked={createSummary}
                onChange={(event) =>
                  setCreateSummary(event.target.checked)
                }
              />

              <span>
                <strong className={style.optionTitle}>
                  회의록 생성
                </strong>
                <span className={style.optionDescription}>
                  회의 내용을 정리하여 AI 회의 요약을 생성합니다.
                </span>
              </span>
            </label>

            <label className={style.option}>
              <input
                className={style.checkbox}
                type="checkbox"
                checked={createNodes}
                onChange={(event) =>
                  setCreateNodes(event.target.checked)
                }
              />

              <span>
                <strong className={style.optionTitle}>
                  노드 생성
                </strong>
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
              onClick={handleClose}
            >
              취소
            </button>

            <button className={style.endButton} type="submit">
              종료
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
