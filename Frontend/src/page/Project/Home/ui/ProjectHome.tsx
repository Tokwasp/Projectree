import MeetingCard from "../components/MeetingCard/MeetingCard";
import style from "../css/ProjectHome.module.css";
import {
  mockProjectHome,
  mockRecentDecisions,
  mockRecentMeetings,
} from "../../../../mocks/ProjectHomeMocks";

function formatDecisionDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

function formatProjectDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
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

      <section
        className={style.section}
        aria-labelledby="recent-meetings-heading"
      >
        <h2 className={style.sectionTitle} id="recent-meetings-heading">
          최근 회의
        </h2>

        {mockRecentMeetings.length === 0 ? (
          <p className={style.meetingEmpty}>최근 회의가 없습니다.</p>
        ) : (
          <div className={style.meetingGrid}>
            {mockRecentMeetings.map((meeting) => (
              <MeetingCard meeting={meeting} key={meeting.meetingId} />
            ))}
          </div>
        )}
      </section>

      <section
        className={style.section}
        aria-labelledby="recent-decisions-heading"
      >
        <h2 className={style.sectionTitle} id="recent-decisions-heading">
          최근 결정사항
        </h2>

        {mockRecentDecisions.length === 0 ? (
          <p className={style.decisionEmpty}>최근 결정사항이 없습니다.</p>
        ) : (
          <div className={style.decisionList}>
            {mockRecentDecisions.map((decision) => (
              <article
                className={style.decisionItem}
                key={decision.decisionId}
              >
                <div className={style.decisionContent}>
                  <h3 className={style.decisionTitle}>{decision.title}</h3>
                  <p className={style.decisionSource}>
                    {decision.sourceMeetingTitle}
                  </p>
                </div>

                <div className={style.decisionMeta}>
                  <span>{decision.authorName}</span>
                  <time dateTime={decision.decidedAt}>
                    {formatDecisionDate(decision.decidedAt)}
                  </time>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
