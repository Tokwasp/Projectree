import style from "./AboutSection.module.css";

const features = [
  {
    number: "01",
    title: "실시간 화상 회의",
    description: "팀원들과 한 공간에서 의견을 나누고 회의를 진행합니다.",
  },
  {
    number: "02",
    title: "AI 회의 정리",
    description: "결정 사항과 할 일을 AI가 자동으로 정리합니다.",
  },
  {
    number: "03",
    title: "아이디어 트리",
    description: "회의에서 나온 생각을 연결해 프로젝트의 흐름을 만듭니다.",
  },
  {
    number: "04",
    title: "프로젝트 관리",
    description: "팀의 기록과 진행 상황을 한눈에 확인합니다.",
  },
];

export default function AboutSection() {
  return (
    <section className={style.about} id="about">
      <div className={style.inner}>
        <div className={style.copy}>
          <p className={style.eyebrow}>ABOUT</p>
          <h2 className={style.title}>
            흩어진 회의 기록을
            <br />
            하나의 흐름으로 연결합니다.
          </h2>
          <p className={style.description}>
            회의에서 나온 결정, 할 일, 아이디어를 한눈에 확인하고
            <br />
            프로젝트의 흐름을 자연스럽게 이어갈 수 있습니다.
          </p>
        </div>

        <div className={style.featureGrid}>
          {features.map((feature) => (
            <article className={style.featureCard} key={feature.number}>
              <span className={style.featureNumber}>{feature.number}</span>
              <h3 className={style.featureTitle}>{feature.title}</h3>
              <p className={style.featureDescription}>
                {feature.description}
              </p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
