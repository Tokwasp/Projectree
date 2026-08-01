import style from "./MeetingParticipantTile.module.css";
import type { MeetingParticipant } from "../../../../../store/meetingStore";

// 색은 토큰만 사용한다
const AVATAR_COLORS = [
  "var(--color-primary)",
  "var(--color-info)",
  "var(--color-success)",
  "var(--color-warning)",
  "var(--color-error)",
];

const colorFor = (identity: string) => {
  let hash = 0;
  for (const character of identity) {
    hash = (hash * 31 + character.charCodeAt(0)) % AVATAR_COLORS.length;
  }
  return AVATAR_COLORS[hash];
};

interface MeetingParticipantTileProps {
  participant: MeetingParticipant;
  speaking: boolean;
}

export default function MeetingParticipantTile({
  participant,
  speaking,
}: MeetingParticipantTileProps) {
  const { identity, name, isLocal, micOn } = participant;

  return (
    <div className={speaking ? style.tileSpeaking : style.tile}>
      <div className={style.avatar} style={{ background: colorFor(identity) }}>
        {name.trim().slice(0, 2) || "?"}
        {!micOn && <span className={style.muted}>음소거</span>}
      </div>
      <span className={style.name}>
        {name}
        {isLocal && " (나)"}
      </span>
    </div>
  );
}
