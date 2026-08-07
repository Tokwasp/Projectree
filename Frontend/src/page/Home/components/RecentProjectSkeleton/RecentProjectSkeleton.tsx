import style from "./RecentProjectSkeleton.module.css";

const SKELETON_CARD_COUNT = 4;

export default function RecentProjectSkeleton() {
  return (
    <div
      className={style.grid}
      role="status"
      aria-label="최근 프로젝트를 불러오는 중입니다."
    >
      {Array.from({ length: SKELETON_CARD_COUNT }, (_, index) => (
        <div className={style.card} key={index} aria-hidden="true">
          <div className={style.visual} />

          <div className={style.content}>
            <div className={style.title} />
            <div className={style.meta} />
          </div>
        </div>
      ))}
    </div>
  );
}