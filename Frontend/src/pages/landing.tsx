import StarfieldBackground from "../components/landing/StarfieldBackground";
import style from "../css/landing/Landing.module.css";

export default function Landing() {
  return (
    <>
      <StarfieldBackground />
      <main>
        <span className={style.title}>Projectree</span>
        <span className={style.info}>회의를 지식으로 변환하세요</span>
        <button className={style.startBtn}>Get Started</button>
      </main>
    </>
  );
}
