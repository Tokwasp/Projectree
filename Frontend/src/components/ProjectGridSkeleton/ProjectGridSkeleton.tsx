import style from "./ProjectGridSkeleton.module.css";

interface ProjectGridSkeletonProps {
  count: number;
  variant?: "default" | "compact";
}

export default function ProjectGridSkeleton({
  count,
  variant = "default",
}: ProjectGridSkeletonProps) {
  return (
    <div
      className={`${style.grid} ${
        variant === "compact" ? style.gridCompact : ""
      }`}
      role="status"
      aria-label="프로젝트 목록을 불러오는 중입니다."
    >
      {Array.from({ length: count }, (_, index) => (
        <div
          className={`${style.card} ${
            variant === "compact" ? style.cardCompact : ""
          }`}
          key={index}
          aria-hidden="true"
        >
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