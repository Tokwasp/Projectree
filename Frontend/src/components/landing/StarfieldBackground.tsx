import { useEffect, useRef } from "react";
import Starfield from "../../lib/starfield.js";
import style from "../../css/landing/StarfieldBackground.module.css";

export default function StarfieldBackground() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    Starfield.setup({
      container,

      // 마우스 자동 추적 비활성화
      auto: false,

      // 항상 화면 중앙
      originX: container.clientWidth / 2,
      originY: container.clientHeight / 2,

      numStars: 250,
      baseSpeed: 3,
      trailLength: 0.8,

      starColor: "rgb(255,255,255)",
      canvasColor: "rgb(0,0,0)",

      hueJitter: 0,

      minSpawnRadius: 80,
      maxSpawnRadius: 500,
    });

    // 처음 한 번만 중앙으로 설정
    Starfield.setOrigin(container.clientWidth / 2, container.clientHeight / 2);

    const handleResize = () => {
      Starfield.resize(container.clientWidth, container.clientHeight);

      Starfield.setOrigin(
        container.clientWidth / 2,
        container.clientHeight / 2,
      );
    };

    // 리사이즈만 처리
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      Starfield.cleanup();
    };
  }, []);

  return <div ref={containerRef} className={style.starfield} />;
}
