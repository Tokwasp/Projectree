import AiFeedback from "../components/AiFeedback/AiFeedback";
import SpeakingDistribution from "../components/SpeakingDistribution/SpeakingDistribution";
import recentMinutesIcon from "../assets/recent_minutes_icon.png";
import style from "../css/ProjectHome.module.css";
import {
  mockAiFeedback,
  mockProjectHome,
  mockRecentMeetings,
  mockSpeakingTimes,
} from "../../../../mocks/ProjectHomeMocks";

function formatProjectDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

function formatMeetingDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    month: "long",
    day: "numeric",
  }).format(new Date(date));
}

export default function ProjectHome() {
  return (
    <div className={style.page}>
      <h1 className={style.introHeading} id="project-intro-heading">
        프로젝트 소개
      </h1>

      <section
        className={style.introCard}
        aria-labelledby="project-intro-heading"
      >
        <h2 className={style.projectName}>{mockProjectHome.title}</h2>
        <p className={style.introDescription}>
          {mockProjectHome.description}
        </p>

        <dl className={style.projectMeta}>
          <div className={style.metaItem}>
            <dt>생성일</dt>
            <dd>{formatProjectDate(mockProjectHome.createdAt)}</dd>
          </div>
          <div className={style.metaItem}>
            <dt>팀원</dt>
            <dd>{mockProjectHome.memberCount}명</dd>
          </div>
        </dl>
      </section>

      <div className={style.dashboardGrid}>
        <AiFeedback feedback={mockAiFeedback} />

        <div className={style.dashboardAside}>
          <section
            className={style.meetingSection}
            aria-labelledby="recent-minutes-heading"
          >
            <div className={style.sectionHeading}>
              <img src={recentMinutesIcon} alt="" />
              <h2 className={style.sectionTitle} id="recent-minutes-heading">
                최근 회의록
              </h2>
            </div>

            {mockRecentMeetings.length === 0 ? (
              <p className={style.meetingEmpty}>최근 회의록이 없습니다.</p>
            ) : (
              <ul className={style.meetingList}>
                {mockRecentMeetings.slice(0, 2).map((meeting) => (
                  <li className={style.meetingItem} key={meeting.meetingId}>
                    <strong>
                      {formatMeetingDate(meeting.scheduledAt)} 회의록
                    </strong>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <SpeakingDistribution speakingTimes={mockSpeakingTimes} />
        </div>
      </div>
    </div>
  );
}
