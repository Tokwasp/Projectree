import { useEffect, useState } from "react";
import {
  TrackEvent,
  createAudioAnalyser,
  type LocalAudioTrack,
} from "livekit-client";

export const MIC_LEVEL_SEGMENTS = 12;

export const useMicLevel = (track: LocalAudioTrack | null, active: boolean) => {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!track || !active) return;

    let frame = 0;
    let analyser: ReturnType<typeof createAudioAnalyser> | null = null;

    const attach = () => {
      void analyser?.cleanup();
      try {
        analyser = createAudioAnalyser(track, { smoothingTimeConstant: 0.6 });
      } catch {
        analyser = null;
        return;
      }

      const context = analyser.analyser.context;
      if (context.state === "suspended" && context instanceof AudioContext) {
        void context.resume();
      }
    };

    const tick = () => {
      if (analyser) {
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

  return track && active ? level : 0;
};
