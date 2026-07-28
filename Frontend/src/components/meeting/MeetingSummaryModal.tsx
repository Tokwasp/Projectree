import {
  useCallback,
  useEffect,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import style from "../../css/meeting/MeetingSummaryModal.module.css";

export interface MeetingSummaryContent {
  overview: string[];
  decisions: string[];
  tasks: string[];
  issues: string[];
}

export interface MeetingSummary {
  meetingId: number;
  title: string;
  date: string;
  duration: string;
  participants: string[];
  content: MeetingSummaryContent;
}

interface MeetingSummaryModalProps {
  isOpen: boolean;
  meeting: MeetingSummary;
  onClose: () => void;
  onSave: (content: MeetingSummaryContent) => void;
}

type SummarySectionKey = keyof MeetingSummaryContent;

interface SummarySection {
  key: SummarySectionKey;
  title: string;
}

const summarySections: SummarySection[] = [
  { key: "overview", title: "전체 요약" },
  { key: "decisions", title: "주요 결정 사항" },
  { key: "tasks", title: "다음 할 일" },
  { key: "issues", title: "이슈 및 논의 사항" },
];

export default function MeetingSummaryModal({
  isOpen,
  meeting,
  onClose,
  onSave,
}: MeetingSummaryModalProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <MeetingSummaryDialog
      meeting={meeting}
      onClose={onClose}
      onSave={onSave}
    />
  );
}

type MeetingSummaryDialogProps = Omit<
  MeetingSummaryModalProps,
  "isOpen"
>;

function MeetingSummaryDialog({
  meeting,
  onClose,
  onSave,
}: MeetingSummaryDialogProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [content, setContent] = useState(meeting.content);

  const isDirty =
    JSON.stringify(content) !== JSON.stringify(meeting.content);

  const handleClose = useCallback(() => {
    if (
      isEditing &&
      isDirty &&
      !window.confirm(
        "수정한 내용이 저장되지 않았습니다. 닫으시겠습니까?",
      )
    ) {
      return;
    }

    setContent(meeting.content);
    setIsEditing(false);
    onClose();
  }, [isDirty, isEditing, meeting.content, onClose]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handleClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleClose]);

  const handleSummaryChange = (
    event: ChangeEvent<HTMLTextAreaElement>,
    sectionKey: SummarySectionKey,
    index: number,
  ) => {
    setContent((currentContent) => ({
      ...currentContent,
      [sectionKey]: currentContent[sectionKey].map(
        (summary, summaryIndex) =>
          summaryIndex === index ? event.target.value : summary,
      ),
    }));
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const normalizeSummaries = (summaries: string[]) =>
      summaries
        .map((summary) => summary.trim())
        .filter(Boolean);

    const normalizedContent: MeetingSummaryContent = {
      overview: normalizeSummaries(content.overview),
      decisions: normalizeSummaries(content.decisions),
      tasks: normalizeSummaries(content.tasks),
      issues: normalizeSummaries(content.issues),
    };

    onSave(normalizedContent);
    setIsEditing(false);
  };

  const hasSummary = summarySections.some(({ key }) =>
    content[key].some((summary) => summary.trim().length > 0),
  );

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
        aria-labelledby="meeting-summary-title"
        onClick={(event) => event.stopPropagation()}
      >
        <form className={style.form} onSubmit={handleSubmit}>
          <header className={style.header}>
            <div>
              <div className={style.titleRow}>
                <h2 className={style.title} id="meeting-summary-title">
                  AI 회의록 검토
                </h2>
                <span className={style.status}>분석 완료</span>
              </div>

              <p className={style.description}>
                AI가 생성한 회의록을 검토하고 수정해 주세요.
              </p>
            </div>

            {!isEditing && (
              <button
                className={style.editButton}
                type="button"
                onClick={() => setIsEditing(true)}
              >
                수정
              </button>
            )}
          </header>

          <div className={style.content}>
            <div className={style.meetingInfo}>
              <strong className={style.meetingTitle}>
                {meeting.title}
              </strong>

              <dl className={style.infoList}>
                <div className={style.infoItem}>
                  <dt>일시</dt>
                  <dd>{meeting.date}</dd>
                </div>

                <div className={style.infoItem}>
                  <dt>진행 시간</dt>
                  <dd>{meeting.duration}</dd>
                </div>

                <div className={style.infoItem}>
                  <dt>참여자</dt>
                  <dd>{meeting.participants.join(", ")}</dd>
                </div>
              </dl>
            </div>

            <div className={style.summaryGrid}>
              {summarySections.map(({ key, title }) => (
                <section
                  className={`${style.summarySection} ${
                    key === "overview" || key === "issues"
                      ? style.wideSection
                      : ""
                  }`}
                  key={key}
                >
                  <h3 className={style.sectionTitle}>{title}</h3>

                  <div className={style.summaryList}>
                    {content[key].map((summary, index) => (
                      <div className={style.summaryItem} key={index}>
                        <span className={style.bullet} aria-hidden="true">
                          •
                        </span>

                        {isEditing ? (
                          <textarea
                            className={style.summaryInput}
                            value={summary}
                            aria-label={`${title} ${index + 1}`}
                            onChange={(event) =>
                              handleSummaryChange(event, key, index)
                            }
                          />
                        ) : (
                          <p>{summary}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>

            <div className={style.notice}>
              저장한 회의록을 바탕으로 세부 노드가 생성됩니다.
            </div>
          </div>

          <footer className={style.footer}>
            <button
              className={style.closeButton}
              type="button"
              onClick={handleClose}
            >
              닫기
            </button>

            {isEditing && (
              <button
                className={style.saveButton}
                type="submit"
                disabled={!hasSummary}
              >
                저장
              </button>
            )}
          </footer>
        </form>
      </section>
    </div>
  );
}
