import { useEffect, useState } from "react";
import {
  TrackEvent,
  createAudioAnalyser,
  type LocalAudioTrack,
} from "livekit-client";

// 막대 개수 — 레벨을 이 단위로 양자화해야 프레임마다 리렌더되지 않는다
export const MIC_LEVEL_SEGMENTS = 12;

/** 마이크가 실제로 소리를 받는지 참여 전에 확인할 수 있게 입력 레벨을 켜진 막대 수로 돌려준다 */
export const useMicLevel = (track: LocalAudioTrack | null, active: boolean) => {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!track || !active) return;

    let frame = 0;
    let analyser: ReturnType<typeof createAudioAnalyser> | null = null;

    // 기기 변경·unmute는 내부 MediaStreamTrack을 교체한다 — 분석기도 다시 만들어야 한다
    const attach = () => {
      void analyser?.cleanup();
      try {
        analyser = createAudioAnalyser(track, { smoothingTimeConstant: 0.6 });
      } catch {
        // AudioContext를 못 만드는 브라우저에서는 미터만 멈춘다 (참여는 막지 않는다)
        analyser = null;
        return;
      }

      // 사용자 클릭 직후라 대개 running이지만, suspended로 열리면 값이 계속 0이다
      const context = analyser.analyser.context;
      if (context.state === "suspended" && context instanceof AudioContext) {
        void context.resume();
      }
    };

    const tick = () => {
      if (analyser) {
        // 말소리는 0~0.3 대역에 몰려 있어 그대로 그리면 막대가 거의 움직이지 않는다
        const volume = Math.min(1, analyser.calculateVolume() * 3);
        setLevel(Math.round(volume * MIC_LEVEL_SEGMENTS));
      }
      frame = requestAnimationFrame(tick);
    };

    attach();
    track.on(TrackEvent.Restarted, attach);
    frame = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frame);
      track.off(TrackEvent.Restarted, attach);
      void analyser?.cleanup();
    };
  }, [track, active]);

  // 꺼졌을 때 0으로 되돌리는 건 effect에서 setState하지 않고 파생으로 처리한다
  // (다시 켜면 rAF 루프가 곧바로 덮어쓴다)
  return track && active ? level : 0;
};
