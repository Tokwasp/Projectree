import style from "./MeetingParticipantTile.module.css";
import { MicOffIcon } from "../MeetingIcons";
import type { MeetingParticipant } from "../../../../../store/meetingStore";

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
      </div>
      <span className={style.name}>
        {!micOn && (
          <span className={style.muted} title="음소거됨">
            <MicOffIcon />
          </span>
        )}
        {name}
        {isLocal && " (나)"}
      </span>
    </div>
  );
}
