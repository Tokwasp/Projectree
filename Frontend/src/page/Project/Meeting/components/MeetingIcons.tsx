/* 아이콘 라이브러리 없이 쓰는 인라인 SVG — 색은 버튼의 color를 그대로 따른다 */
/* prejoin 모달과 회의 오버레이가 같은 아이콘을 쓰므로 한곳에 모아 둔다 */
const iconProps = {
  width: 20,
  height: 20,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

export function MicOnIcon() {
  return (
    <svg {...iconProps}>
      <rect x="9" y="2" width="6" height="11" rx="3" />
      <path d="M5 10v1a7 7 0 0 0 14 0v-1" />
      <line x1="12" y1="19" x2="12" y2="22" />
    </svg>
  );
}

export function MicOffIcon() {
  return (
    <svg {...iconProps}>
      <path d="M15 9.34V5a3 3 0 0 0-5.94-.6" />
      <path d="M9 9v4a3 3 0 0 0 5.12 2.12" />
      <path d="M17 16.95A7 7 0 0 1 5 11v-1" />
      <path d="M19 11v-1" />
      <line x1="12" y1="19" x2="12" y2="22" />
      <line x1="3" y1="3" x2="21" y2="21" />
    </svg>
  );
}

export function CamOnIcon() {
  return (
    <svg {...iconProps}>
      <path d="m22 8-6 4 6 4V8Z" />
      <rect x="2" y="6" width="14" height="12" rx="2" />
    </svg>
  );
}

export function CamOffIcon() {
  return (
    <svg {...iconProps}>
      <path d="M10.66 6H14a2 2 0 0 1 2 2v2.34l1 1L22 8v8" />
      <path d="M16 16a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h2" />
      <line x1="2" y1="2" x2="22" y2="22" />
    </svg>
  );
}

export function ScreenOnIcon() {
  return (
    <svg {...iconProps}>
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8" />
      <path d="M12 17v4" />
      <path d="m12 7-3 3h6l-3-3v6" />
    </svg>
  );
}

export function ScreenOffIcon() {
  return (
    <svg {...iconProps}>
      <path d="M22 15V5a2 2 0 0 0-2-2H8" />
      <path d="M4 3a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h13" />
      <path d="M8 21h8" />
      <path d="M12 17v4" />
      <line x1="2" y1="2" x2="22" y2="22" />
    </svg>
  );
}

export function LeaveIcon() {
  return (
    <svg {...iconProps}>
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="m16 17 5-5-5-5" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}
