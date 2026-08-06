import { useParams } from "react-router-dom";
import { useAuthStore } from "../../../../store/authStore";
import { mockProjectHome } from "../../../../mocks/ProjectHomeMocks";
import AiFeedback from "../components/AiFeedback/AiFeedback";
import SpeakingDistribution from "../components/SpeakingDistribution/SpeakingDistribution";
import useProjectHome from "../hooks/useProjectHome";
import recentMinutesIcon from "../assets/recent_minutes_icon.png";
import style from "../css/ProjectHome.module.css";

function formatProjectDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

export default function ProjectHome() {
  const { projectId } = useParams<{ projectId: string }>();
  const parsedProjectId = Number(projectId);
  const validProjectId =
    Number.isInteger(parsedProjectId) && parsedProjectId > 0
      ? parsedProjectId
      : null;
  const currentUserName = useAuthStore((state) => state.name);
  const { data, isLoading, error } = useProjectHome(validProjectId);

  const feedback = {
    details: data?.myReview
      ? [
          {
            label: "말하기 속도",
            description: data.myReview.speedFeedback,
          },
          {
            label: "개인 피드백",
            description: data.myReview.personalFeedback,
          },
          {
            label: "종합 피드백",
            description: data.myReview.overallFeedback,
          },
        ]
      : [],
  };

  const speakingTimes =
    data?.personalSpeakingList.map((member, index) => ({
      memberId: index,
      name: member.name,
      percentage: member.speakPercent,
      isCurrentUser: member.name === currentUserName,
    })) ?? [];
  const meetingRecords = data?.meetingRecordList ?? [];

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

      {isLoading ? (
        <p className={style.meetingEmpty}>
          프로젝트 홈을 불러오는 중입니다.
        </p>
      ) : error ? (
        <p className={style.meetingEmpty} role="alert">
          {error}
        </p>
      ) : (
        <div className={style.dashboardGrid}>
          <AiFeedback feedback={feedback} />

          <div className={style.dashboardAside}>
            <section
              className={style.meetingSection}
              aria-labelledby="recent-minutes-heading"
            >
              <div className={style.sectionHeading}>
                <img src={recentMinutesIcon} alt="" />
                <h2
                  className={style.sectionTitle}
                  id="recent-minutes-heading"
                >
                  최근 회의록
                </h2>
              </div>

              {meetingRecords.length === 0 ? (
                <p className={style.meetingEmpty}>
                  최근 회의록이 없습니다.
                </p>
              ) : (
                <ul className={style.meetingList}>
                  {meetingRecords.slice(0, 2).map((meeting, index) => (
                    <li
                      className={style.meetingItem}
                      key={`${meeting.name}-${index}`}
                    >
                      <strong>{meeting.name}</strong>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <SpeakingDistribution speakingTimes={speakingTimes} />
          </div>
        </div>
      )}
    </div>
  );
}
