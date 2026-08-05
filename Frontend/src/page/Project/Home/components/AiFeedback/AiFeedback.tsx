import type { AiFeedbackSummary } from "../../../../../types/ProjectHome";
import aiFeedbackFace from "../../assets/ai_feedback_face.png";
import aiFeedbackIcon from "../../assets/ai_feedback_icon.png";
import style from "./AiFeedback.module.css";

interface AiFeedbackProps {
  feedback: AiFeedbackSummary;
}

export default function AiFeedback({ feedback }: AiFeedbackProps) {
  return (
    <section className={style.card} aria-labelledby="ai-feedback-heading">
      <div className={style.heading}>
        <img src={aiFeedbackIcon} alt="" />
        <h2 className={style.title} id="ai-feedback-heading">
          AI 개인 피드백
        </h2>
      </div>
      <div className={style.summary}>
        <img
          className={style.feedbackFace}
          src={aiFeedbackFace}
          alt="긍정적인 AI 피드백"
        />
      </div>
      <ul className={style.detailList}>
        {feedback.details.map((detail) => (
          <li className={style.detailItem} key={detail.label}>
            <strong>{detail.label}</strong>
            <span>{detail.description}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
