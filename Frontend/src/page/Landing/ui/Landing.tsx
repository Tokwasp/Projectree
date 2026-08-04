import Footer from "../../../components/Footer/Footer";
import AboutSection from "../components/AboutSection/AboutSection";
import FeatureShowcaseSection from "../components/FeatureShowcaseSection/FeatureShowcaseSection";
import HowItWorksSection from "../components/HowItWorksSection/HowItWorksSection";
import StatsSection from "../components/StatsSection/StatsSection";
import StarfieldBackground from "../components/StarfieldBackground/StarfieldBackground";
import style from "../css/Landing.module.css";
import { useLoginModalStore } from "../../../store/loginModalStore";

export default function Landing() {
  const { openLoginModal } = useLoginModalStore();

  return (
    <main className={style.landing}>
      <section className={style.hero}>
        <StarfieldBackground />

        <div className={style.heroContent}>
          <h1 className={style.title}>Projectree</h1>
          <p className={style.info}>
            <span className={style.typingText}>
              당신의 프로젝트를 시각화하세요.
            </span>
          </p>

          <button className={style.startBtn} onClick={openLoginModal}>
            Get Started
          </button>
        </div>

        <div className={style.eclipseBlur} />
        <a
          className={style.scrollGuide}
          href="#about"
          aria-label="Projectree 소개 영역으로 이동"
        >
          <span className={style.scrollArrow} aria-hidden="true" />
        </a>
      </section>

      <AboutSection />
      <StatsSection />
      <FeatureShowcaseSection />
      <HowItWorksSection />
      <Footer />
    </main>
  );
}
