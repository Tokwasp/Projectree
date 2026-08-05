import { useEffect, useRef } from "react";
import AiSummaryIcon from "../../assets/ai_summary_icon.png";
import ProjectFlowIcon from "../../assets/project_flow_icon.png";
import ProjectFlowPreview from "../../assets/project_flow_preview.png";
import style from "./FeatureShowcaseSection.module.css";

const summaryItems = [
  {
    icon: "✦",
    text: "회의 요약 생성",
  },
  {
    icon: "✓",
    text: "결정 사항 3건 추출",
  },
  {
    icon: "!",
    text: "이슈 5건 추출",
  },
];

export default function FeatureShowcaseSection() {
  const rowRefs = useRef<HTMLElement[]>([]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;

          entry.target.classList.add(style.visible);
          observer.unobserve(entry.target);
        });
      },
      {
        threshold: 0.2,
        rootMargin: "0px 0px -10%",
      },
    );

    const rows = rowRefs.current;
    rows.forEach((row) => observer.observe(row));

    return () => {
      rows.forEach((row) => observer.unobserve(row));
      observer.disconnect();
    };
  }, []);

  return (
    <section
      className={style.showcase}
      aria-label="Projectree 핵심 기능 소개"
    >
      <article
        ref={(element) => {
          if (element) rowRefs.current[0] = element;
        }}
        className={`${style.featureRow} ${style.revealItem}`}
      >
        <div className={style.copy}>
          <span className={style.iconBox} aria-hidden="true">
            <img className={style.iconImage} src={AiSummaryIcon} alt="" />
          </span>

          <h2 className={style.title}>AI가 회의를 대신 정리합니다</h2>

          <p className={style.description}>
            화상 회의가 끝나면 AI가 핵심 내용을 요약하고,
            <br />
            참여자 발언에서 결정 사항과 할 일을 자동으로 골라냅니다.
          </p>
        </div>

        <div
          className={style.summaryPanel}
          role="group"
          aria-label="AI 회의 정리 예시"
        >
          {summaryItems.map((item) => (
            <div className={style.summaryItem} key={item.text}>
              <span className={style.summaryIcon} aria-hidden="true">
                {item.icon}
              </span>
              <span>{item.text}</span>
            </div>
          ))}
        </div>
      </article>

      <article
        ref={(element) => {
          if (element) rowRefs.current[1] = element;
        }}
        className={`${style.featureRow} ${style.reverse} ${style.revealItem}`}
      >
        <div className={style.imageFrame}>
          <img
            className={style.projectImage}
            src={ProjectFlowPreview}
            alt="노드로 연결된 프로젝트 흐름"
            loading="lazy"
            decoding="async"
          />
        </div>

        <div className={style.copy}>
          <span className={style.iconBox} aria-hidden="true">
            <img
              className={`${style.iconImage} ${style.flowIcon}`}
              src={ProjectFlowIcon}
              alt=""
              loading="lazy"
              decoding="async"
            />
          </span>

          <h2 className={style.title}>노드로 연결되는 프로젝트 흐름</h2>

          <p className={style.description}>
            회의에서 나온 결정, 할 일, 이슈의 연결을
            <br />
            그래프로 한눈에 확인합니다.
          </p>
        </div>
      </article>
    </section>
  );
}
