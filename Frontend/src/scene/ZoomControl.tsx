import { useEffect, useRef } from "react";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";

interface ZoomControlProps {
  controlsRef: React.RefObject<OrbitControlsImpl | null>;
  minDistance: number;
  maxDistance: number;
}

const STEP = 2;

/** A vertical zoom slider pinned to the bottom-right corner, so users can
 * zoom without reaching for the scroll wheel. It reads/writes the camera
 * distance straight off the OrbitControls instance each frame via a plain
 * rAF loop (not tied to R3F's loop, since this lives outside the Canvas),
 * so dragging it and wheel-zooming stay in sync without React re-renders. */
export function ZoomControl({ controlsRef, minDistance, maxDistance }: ZoomControlProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const draggingRef = useRef(false);

  useEffect(() => {
    let rafId: number;
    const tick = () => {
      const controls = controlsRef.current;
      if (controls && inputRef.current && !draggingRef.current) {
        // Invert so sliding up (toward "+") zooms in, matching the button labels.
        const inverted = maxDistance + minDistance - controls.getDistance();
        inputRef.current.value = inverted.toString();
      }
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, [controlsRef, minDistance, maxDistance]);

  const setDistance = (distance: number) => {
    const controls = controlsRef.current;
    if (!controls) return;
    const camera = controls.object;
    const clamped = Math.min(maxDistance, Math.max(minDistance, distance));
    const direction = camera.position.clone().sub(controls.target).normalize();
    camera.position.copy(controls.target).addScaledVector(direction, clamped);
    controls.update();
  };

  const handleSliderChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const inverted = Number(event.target.value);
    setDistance(maxDistance + minDistance - inverted);
  };

  const step = (sign: 1 | -1) => {
    const controls = controlsRef.current;
    if (!controls) return;
    setDistance(controls.getDistance() - sign * STEP);
  };

  return (
    <div
      style={{
        position: "absolute",
        right: 24,
        bottom: 28,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 6,
        zIndex: 20,
        fontFamily: "'Pretendard', 'Segoe UI', system-ui, -apple-system, sans-serif",
        userSelect: "none",
      }}
    >
      <button type="button" onClick={() => step(1)} style={zoomButtonStyle}>
        +
      </button>

      <div style={{ width: 32, height: 140, position: "relative" }}>
        <input
          ref={inputRef}
          type="range"
          min={minDistance}
          max={maxDistance}
          step={0.1}
          defaultValue={(minDistance + maxDistance) / 2}
          onPointerDown={() => (draggingRef.current = true)}
          onPointerUp={() => (draggingRef.current = false)}
          onChange={handleSliderChange}
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: 140,
            height: 24,
            margin: 0,
            transform: "translate(-50%, -50%) rotate(-90deg)",
            accentColor: "#7fd8ff",
            cursor: "pointer",
          }}
        />
      </div>

      <button type="button" onClick={() => step(-1)} style={zoomButtonStyle}>
        −
      </button>
    </div>
  );
}

const zoomButtonStyle: React.CSSProperties = {
  width: 26,
  height: 26,
  borderRadius: "50%",
  border: "1px solid rgba(127, 216, 255, 0.4)",
  background: "rgba(6, 8, 20, 0.55)",
  backdropFilter: "blur(3px)",
  color: "#f2f4ff",
  fontSize: 15,
  lineHeight: 1,
  cursor: "pointer",
};
