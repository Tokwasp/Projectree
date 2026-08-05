import style from "./StatsSection.module.css";

const stats = [
  {
    value: "약 1~2분",
    label: "회의록 요약 생성 시간",
  },
  {
    value: "자동",
    label: "결정 · 할 일 · 이슈 분류",
  },
  {
    value: "한눈에",
    label: "프로젝트 맥락 확인",
  },
];

export default function StatsSection() {
  return (
    <section className={style.stats} aria-label="Projectree 주요 특징">
      <div className={style.inner}>
        {stats.map((stat) => (
          <div className={style.statItem} key={stat.value}>
            <strong className={style.value}>{stat.value}</strong>
            <span className={style.marker} />
            <p className={style.label}>{stat.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
