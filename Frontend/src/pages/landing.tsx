import StarfieldBackground from "../components/landing/StarfieldBackground";
import style from "../css/landing/Landing.module.css";
import { useLoginModal } from "../contexts/LoginModalContext";

export default function Landing() {
  const { openLoginModal } = useLoginModal();

  return (
    <>
      <StarfieldBackground />
      <main>
        <span className={style.title}>Projectree</span>
        <span className={style.info}>당신의 프로젝트를 시각화하세요</span>
        <button className={style.startBtn} onClick={openLoginModal}>
          Get Started
        </button>
      </main>
      <div className={style.eclipseBlur} />
    </>
  );
}
