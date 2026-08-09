import style from "./MyProjectListSkeleton.module.css";

const SKELETON_ROW_COUNT = 6;

export default function MyProjectListSkeleton() {
  return (
    <div
      className={style.list}
      role="status"
      aria-label="참여 중인 프로젝트를 불러오는 중입니다."
    >
      {Array.from({ length: SKELETON_ROW_COUNT }, (_, index) => (
        <div className={style.row} key={index} aria-hidden="true">
          <div className={style.thumbnail} />

          <div className={style.copy}>
            <div className={style.name} />
            <div className={style.memberCount} />
          </div>

          <div className={style.arrow} />
        </div>
      ))}
    </div>
  );
}