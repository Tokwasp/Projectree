interface ViewModeToggleProps {
  is2D: boolean;
  onToggle: () => void;
}

/** Top-right pill that flips between the free-orbiting 3D view and a locked
 * front-on 2D view, for users who find tumbling 3D navigation uncomfortable. */
export function ViewModeToggle({ is2D, onToggle }: ViewModeToggleProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      style={{
        position: "absolute",
        top: 24,
        right: 24,
        zIndex: 20,
        padding: "8px 18px",
        borderRadius: 999,
        border: "1px solid rgba(127, 216, 255, 0.4)",
        background: "rgba(6, 8, 20, 0.55)",
        backdropFilter: "blur(3px)",
        color: "#f2f4ff",
        fontSize: 13,
        fontFamily: "'Pretendard', 'Segoe UI', system-ui, -apple-system, sans-serif",
        letterSpacing: "0.02em",
        cursor: "pointer",
        userSelect: "none",
      }}
    >
      {is2D ? "3D로 보기" : "2D로 보기"}
    </button>
  );
}
