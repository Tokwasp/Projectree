import { useEffect, useRef } from "react";
import type { CSSProperties } from "react";
import style from "./MeetingOverlay.module.css";
import MeetingParticipantTile from "../MeetingParticipantTile/MeetingParticipantTile";
import { useMeetingStore } from "../../../../../store/meetingStore";
import { getVideoTrack } from "../../../../../utils/meetingSession";
import {
  formatElapsed,
  useMeetingOverlay,
} from "../../hooks/useMeetingOverlay";

export default function MeetingOverlay() {
  const phase = useMeetingStore((state) => state.phase);
  const roomName = useMeetingStore((state) => state.roomName);
  const participants = useMeetingStore((state) => state.participants);
  const speakers = useMeetingStore((state) => state.speakers);
  const videoTiles = useMeetingStore((state) => state.videoTiles);
  const micOn = useMeetingStore((state) => state.micOn);
  const camOn = useMeetingStore((state) => state.camOn);
  const screenOn = useMeetingStore((state) => state.screenOn);
  const needSound = useMeetingStore((state) => state.needSound);

  const {
    isImmersive,
    elapsed,
    miniPos,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    expand,
    leave,
    finish,
    toggleMic,
    toggleCam,
    toggleScreen,
    activateSound,
  } = useMeetingOverlay();

  const gridRef = useRef<HTMLDivElement | null>(null);

  // 트랙 부착은 React 밖의 일이라 직접 붙인다. srcObject가 있으면 이미 붙은 것
  useEffect(() => {
    videoTiles.forEach((tile) => {
      const element = gridRef.current?.querySelector<HTMLVideoElement>(
        `video[data-tile="${tile.id}"]`,
      );
      const track = getVideoTrack(tile.id);

      if (element && track && !element.srcObject) track.attach(element);
    });
  }, [videoTiles]);

  if (phase === "idle") return null;

  const containerClass = [
    style.container,
    isImmersive ? style.immersive : style.mini,
    phase === "connecting" ? style.hidden : "",
  ].join(" ");

  const position =
    !isImmersive && miniPos
      ? ({
          "--mini-x": `${miniPos.x}px`,
          "--mini-y": `${miniPos.y}px`,
        } as CSSProperties)
      : undefined;

  return (
    <section className={containerClass} style={position} aria-label="화상 회의">
      <header
        className={style.header}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
      >
        <span className={style.recording}>녹음 중</span>
        {isImmersive && (
          <span className={style.roomName}>
            회의방 · {roomName?.slice(0, 8)}…
          </span>
        )}
        <span className={style.meta}>
          {formatElapsed(elapsed)} · {participants.length}명
        </span>
        {!isImmersive && (
          <button className={style.expand} type="button" onClick={expand}>
            펼치기
          </button>
        )}
      </header>

      {needSound && (
        <button
          className={style.soundBanner}
          type="button"
          onClick={activateSound}
        >
          브라우저가 소리를 막았습니다 — 눌러서 상대 목소리 듣기
        </button>
      )}

      <div className={style.stage}>
        {/* 그리드는 항상 마운트 유지 — 교체하면 붙인 video 요소가 사라진다 */}
        <div className={style.videoGrid} ref={gridRef}>
          {videoTiles.map((tile) => (
            <div className={style.videoTile} key={tile.id}>
              <video
                className={tile.mirrored ? style.mirrored : undefined}
                data-tile={tile.id}
                autoPlay
                playsInline
                muted={tile.id.startsWith("local-")}
              />
              <span className={style.videoLabel}>{tile.label}</span>
            </div>
          ))}
        </div>

        <div className={style.roster}>
          {participants.map((participant) => (
            <MeetingParticipantTile
              key={participant.identity}
              participant={participant}
              speaking={speakers.includes(participant.identity)}
            />
          ))}
        </div>
      </div>

      <footer className={style.controls}>
        <button
          className={micOn ? style.control : style.controlOff}
          type="button"
          onClick={toggleMic}
        >
          {micOn ? "마이크" : "음소거됨"}
        </button>

        {isImmersive && (
          <>
            <button
              className={camOn ? style.controlActive : style.control}
              type="button"
              onClick={toggleCam}
            >
              카메라
            </button>
            <button
              className={screenOn ? style.controlActive : style.control}
              type="button"
              onClick={toggleScreen}
            >
              화면공유
            </button>
          </>
        )}

        <button className={style.leave} type="button" onClick={leave}>
          나가기
        </button>
        <button className={style.finish} type="button" onClick={finish}>
          회의 종료
        </button>
      </footer>
    </section>
  );
}
