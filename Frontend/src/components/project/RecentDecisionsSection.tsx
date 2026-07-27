import type { RecentDecisionSummary } from "../../types/ProjectHome";
import style from "../../css/project/RecentDecisionsSection.module.css";

interface RecentDecisionsSectionProps {
  decisions: RecentDecisionSummary[];
  onViewAll?: () => void;
}

function formatDecisionDate(date: string) {
  return new Intl.DateTimeFormat("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(date));
}

export default function RecentDecisionsSection({
  decisions,
  onViewAll,
}: RecentDecisionsSectionProps) {
  return (
    <section
      className={style.section}
      aria-labelledby="recent-decisions-heading"
    >
      <div className={style.header}>
        <h2 className={style.title} id="recent-decisions-heading">
          최근 결정사항
        </h2>

        {onViewAll && (
          <button
            className={style.viewAllButton}
            type="button"
            onClick={onViewAll}
          >
            전체 결정사항 보기
          </button>
        )}
      </div>

      {decisions.length === 0 ? (
        <p className={style.emptyMessage}>
          최근 결정사항이 없습니다.
        </p>
      ) : (
        <div className={style.list}>
          {decisions.map((decision) => (
            <article
              className={style.item}
              key={decision.decisionId}
            >
              <div className={style.content}>
                <h3 className={style.decisionTitle}>
                  {decision.title}
                </h3>
                <p className={style.source}>
                  {decision.sourceMeetingTitle}
                </p>
              </div>

              <div className={style.meta}>
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
  );
}
