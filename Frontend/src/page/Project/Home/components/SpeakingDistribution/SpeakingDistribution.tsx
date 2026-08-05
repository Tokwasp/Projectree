import type { SpeakingTimeSummary } from "../../../../../types/ProjectHome";
import style from "./SpeakingDistribution.module.css";

interface SpeakingDistributionProps {
  speakingTimes: SpeakingTimeSummary[];
}

export default function SpeakingDistribution({
  speakingTimes,
}: SpeakingDistributionProps) {
  return (
    <section
      className={style.card}
      aria-labelledby="speaking-distribution-heading"
    >
      <div className={style.headingGroup}>
        <h2 className={style.title} id="speaking-distribution-heading">
          발화 시간 분포
        </h2>
        <p>최근 회의에서 팀원별 발화 비율을 확인해보세요.</p>
      </div>

      <ul className={style.memberList}>
        {speakingTimes.map((member) => (
          <li className={style.memberItem} key={member.memberId}>
            <span className={style.avatar} aria-hidden="true">
              {member.name.slice(0, 1)}
            </span>
            <span className={style.memberName}>
              {member.name}
              {member.isCurrentUser && <strong>나</strong>}
            </span>
            <progress
              className={style.progress}
              max="100"
              value={member.percentage}
              aria-label={`${member.name} 발화 비율 ${member.percentage}%`}
            />
            <span className={style.percentage}>{member.percentage}%</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
