import { useEffect, useRef } from "react";
import style from "./HowItWorksSection.module.css";

const steps = [
  {
    number: "01",
    title: "프로젝트 시작",
    description: "프로젝트를 만들고 함께할 팀원을 초대합니다.",
  },
  {
    number: "02",
    title: "실시간 회의",
    description:
      "팀원들과 화상 회의를 진행하며 의견과 아이디어를 나눕니다.",
  },
  {
    number: "03",
    title: "AI 회의 정리",
    description:
      "회의가 끝나면 AI가 요약, 결정 사항, 할 일을 정리합니다.",
  },
  {
    number: "04",
    title: "프로젝트 흐름 연결",
    description:
      "정리된 내용을 노드로 연결해 프로젝트의 전체 맥락을 확인합니다.",
  },
];

export default function HowItWorksSection() {
  const stepRefs = useRef<HTMLLIElement[]>([]);

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;

          entry.target.classList.add(style.visible);
          entry.target.parentElement?.classList.add(style.timelineVisible);
          observer.unobserve(entry.target);
        });
      },
      {
        threshold: 0.3,
        rootMargin: "0px 0px -10%",
      },
    );

    const stepElements = stepRefs.current;
    stepElements.forEach((step) => observer.observe(step));

    return () => {
      stepElements.forEach((step) => observer.unobserve(step));
      observer.disconnect();
    };
  }, []);

  return (
    <section
      className={style.howItWorks}
      aria-labelledby="how-it-works-title"
    >
      <div className={style.heading}>
        <p className={style.eyebrow}>HOW IT WORKS</p>
        <h2 className={style.title} id="how-it-works-title">
          아이디어가 프로젝트의
          <br />
          흐름이 되기까지
        </h2>
      </div>

      <ol className={style.timeline}>
        {steps.map((step, index) => {
          const position = index % 2 === 0 ? style.left : style.right;

          return (
            <li
              ref={(element) => {
                if (element) stepRefs.current[index] = element;
              }}
              className={`${style.step} ${position}`}
              key={step.number}
            >
              <article className={style.card}>
                <span className={style.stepNumber}>STEP {step.number}</span>
                <h3 className={style.stepTitle}>{step.title}</h3>
                <p className={style.stepDescription}>{step.description}</p>
              </article>

              <span className={style.marker} aria-hidden="true">
                {step.number}
              </span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
