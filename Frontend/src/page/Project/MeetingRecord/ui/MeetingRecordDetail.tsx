import { Link, useParams } from "react-router-dom";
import useMeetingRecordDetail from "../hooks/useMeetingRecordDetail";
import style from "../css/MeetingRecordDetail.module.css";

interface DetailSectionProps {
  title: string;
  items: string[];
  emptyMessage: string;
  variant: "summary" | "decision" | "todo" | "issue";
}

function formatMeetingDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
  }).format(new Date(date));
}

function formatMeetingTime(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(date));
}

function DetailSection({
  title,
  items,
  emptyMessage,
  variant,
}: DetailSectionProps) {
  const variantClassName = {
    summary: style.summarySection,
    decision: style.decisionSection,
    todo: style.todoSection,
    issue: style.issueSection,
  }[variant];

  return (
    <section className={`${style.detailSection} ${variantClassName}`}>
      <div className={style.sectionHeading}>
        <h2>{title}</h2>
      </div>

      {items.length === 0 ? (
        <p className={style.emptyContent}>{emptyMessage}</p>
      ) : (
        <ul>
          {items.map((item, index) => (
            <li key={`${title}-${index}`}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function MeetingRecordDetail() {
  const { projectId, meetingId } = useParams<{
    projectId: string;
    meetingId: string;
  }>();

  const parsedProjectId = Number(projectId);
  const parsedMeetingId = Number(meetingId);

  const validProjectId =
    Number.isInteger(parsedProjectId) && parsedProjectId > 0
      ? parsedProjectId
      : null;
  const validMeetingId =
    Number.isInteger(parsedMeetingId) && parsedMeetingId > 0
      ? parsedMeetingId
      : null;

  const { data, isLoading, error } = useMeetingRecordDetail(
    validProjectId,
    validMeetingId,
  );

  if (isLoading) {
    return (
      <p className={style.stateMessage}>
        회의록을 불러오는 중입니다.
      </p>
    );
  }

  if (error || !data) {
    return (
      <p className={style.stateMessage} role="alert">
        {error ?? "회의록 정보를 불러오지 못했습니다."}
      </p>
    );
  }

  return (
    <div className={style.page}>
      <nav className={style.detailNavigation} aria-label="회의록 이동">
        <Link
          className={style.backLink}
          to={`/projects/${data.projectId}`}
        >
          ← 프로젝트 홈
        </Link>
        <Link
          className={style.listLink}
          to={`/projects/${data.projectId}/meetings/records`}
        >
          전체 회의록 보기
        </Link>
      </nav>

      <article className={style.document}>
        <header className={style.header}>
          <div className={style.titleGroup}>
            <span className={style.label}>회의록</span>
            <h1>{data.title}</h1>
          </div>

          <dl className={style.meetingMeta}>
            <div>
              <dt>회의 일자</dt>
              <dd>{formatMeetingDate(data.meetingDate)}</dd>
            </div>
            <div>
              <dt>회의 시간</dt>
              <dd>
                {formatMeetingTime(data.startedAt)}–
                {formatMeetingTime(data.endedAt)}
              </dd>
            </div>
            <div>
              <dt>진행 시간</dt>
              <dd>{data.durationMinutes}분</dd>
            </div>
          </dl>
        </header>

        <main className={style.content}>
          <DetailSection
            title="회의 요약"
            items={data.summary}
            emptyMessage="등록된 회의 요약이 없습니다."
            variant="summary"
          />

          <div className={style.actionGrid}>
            <DetailSection
              title="결정 사항"
              items={data.decisions}
              emptyMessage="등록된 결정 사항이 없습니다."
              variant="decision"
            />

            <DetailSection
              title="다음 할 일"
              items={data.nextTodos}
              emptyMessage="등록된 다음 할 일이 없습니다."
              variant="todo"
            />
          </div>

          <DetailSection
            title="논의 이슈"
            items={data.issues}
            emptyMessage="등록된 논의 이슈가 없습니다."
            variant="issue"
          />
        </main>
      </article>
    </div>
  );
}
