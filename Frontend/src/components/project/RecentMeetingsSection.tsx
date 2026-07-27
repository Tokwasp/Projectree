import type { RecentMeetingSummary } from "../../types/ProjectHome";
import MeetingCard from "./MeetingCard";
import style from "../../css/project/RecentMeetingsSection.module.css";

interface RecentMeetingsSectionProps {
  meetings: RecentMeetingSummary[];
  onViewAll?: () => void;
}

export default function RecentMeetingsSection({
  meetings,
  onViewAll,
}: RecentMeetingsSectionProps) {
  return (
    <section
      className={style.section}
      aria-labelledby="recent-meetings-heading"
    >
      <div className={style.header}>
        <h2
          className={style.title}
          id="recent-meetings-heading"
        >
          최근 회의
        </h2>

        {onViewAll && (
          <button
            className={style.viewAllButton}
            type="button"
            onClick={onViewAll}
          >
            전체 회의 보기
          </button>
        )}
      </div>

      {meetings.length === 0 ? (
        <p className={style.emptyMessage}>
          최근 회의가 없습니다.
        </p>
      ) : (
        <div className={style.grid}>
          {meetings.map((meeting) => (
            <MeetingCard
              meeting={meeting}
              key={meeting.meetingId}
            />
          ))}
        </div>
      )}
    </section>
  );
}