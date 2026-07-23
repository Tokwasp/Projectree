import StarfieldBackground from "../components/landing/StarfieldBackground";
import style from "../css/landing/Landing.module.css";

export default function Landing() {
  return (
    <>
      <StarfieldBackground />
      <main>
        <span className={style.title}>Projectree</span>
        <span className={style.info}>당신의 프로젝트를 시각화하세요</span>
        <button className={style.startBtn}>Get Started</button>
      </main>
    </>
  );
}
