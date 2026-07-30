import StarfieldBackground from "../components/StarfieldBackground/StarfieldBackground";
import style from "../css/Landing.module.css";
import { useLoginModalStore } from "../../../store/loginModalStore";

export default function Landing() {
  const { openLoginModal } = useLoginModalStore();

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
