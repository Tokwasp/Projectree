import { useEffect, useState } from "react";
import {
  TrackEvent,
  createAudioAnalyser,
  type LocalAudioTrack,
} from "livekit-client";

export const MIC_LEVEL_SEGMENTS = 12;

// 이 진폭 아래는 무음처리
const NOISE_FLOOR = 0.05;
// 최대 소리
const FULL_SCALE = 0.15;
const RELEASE = 0.85;

export const useMicLevel = (track: LocalAudioTrack | null, active: boolean) => {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!track || !active) return;

    let frame = 0;
    let analyser: ReturnType<typeof createAudioAnalyser> | null = null;
    let buffer = new Uint8Array(0);
    let smoothed = 0;
    let lastLevel = -1;

    const attach = () => {
      void analyser?.cleanup();
      try {
        analyser = createAudioAnalyser(track, { fftSize: 1024 });
      } catch {
        analyser = null;
        return;
      }

      buffer = new Uint8Array(analyser.analyser.fftSize);

      const context = analyser.analyser.context;
      if (context.state === "suspended" && context instanceof AudioContext) {
        void context.resume();
      }
    };

    const measure = () => {
      if (!analyser) return 0;

      analyser.analyser.getByteTimeDomainData(buffer);

      let sum = 0;
      for (const sample of buffer) {
        const deviation = (sample - 128) / 128;
        sum += deviation * deviation;
      }
      return Math.sqrt(sum / buffer.length);
    };

    const tick = () => {
      const rms = measure();
      smoothed =
        rms > smoothed ? rms : smoothed * RELEASE + rms * (1 - RELEASE);

      const ratio = (smoothed - NOISE_FLOOR) / (FULL_SCALE - NOISE_FLOOR);
      const next = Math.round(
        Math.min(1, Math.max(0, ratio)) * MIC_LEVEL_SEGMENTS,
      );

      if (next !== lastLevel) {
        lastLevel = next;
        setLevel(next);
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
