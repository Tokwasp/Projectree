import type { RecentMeetingSummary } from "../../types/ProjectHome";
import style from "../../css/project/MeetingCard.module.css";

interface MeetingCardProps {
  meeting: RecentMeetingSummary;
}

function formatMeetingDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "2-digit",
    day: "2-digit",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(date));
}

export default function MeetingCard({
  meeting,
}: MeetingCardProps) {
  return (
    <article className={style.card}>
      <h3 className={style.title}>{meeting.title}</h3>

      <time
        className={style.date}
        dateTime={meeting.scheduledAt}
      >
        {formatMeetingDate(meeting.scheduledAt)}
      </time>

      <p className={style.summary}>{meeting.summary}</p>
      <span className={style.host}>진행자 {meeting.hostName}</span>
    </article>
  );
}
