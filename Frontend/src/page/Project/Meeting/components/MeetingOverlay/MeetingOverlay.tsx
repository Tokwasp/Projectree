import { useCallback, useState } from "react";
import type { CSSProperties } from "react";
import style from "./MeetingOverlay.module.css";
import MeetingParticipantTile from "../MeetingParticipantTile/MeetingParticipantTile";
import MeetingEndModal from "../MeetingEndModal/MeetingEndModal";
import {
  CamOffIcon,
  CamOnIcon,
  LeaveIcon,
  MicOffIcon,
  MicOnIcon,
  ScreenOffIcon,
  ScreenOnIcon,
} from "../MeetingIcons";
import { useMeetingStore } from "../../../../../store/meetingStore";
import type {
  MeetingParticipant,
  MeetingVideoTile,
} from "../../../../../store/meetingStore";
import { getVideoTrack } from "../../../../../utils/meetingSession";
import {
  formatElapsed,
  useMeetingOverlay,
} from "../../hooks/useMeetingOverlay";

const MAX_GRID_CELLS = 12;
const MAX_FILMSTRIP_CELLS = 5;

const gridShape = (count: number) => {
  if (count <= 1) return { cols: 1, rows: 1 };
  if (count === 2) return { cols: 2, rows: 1 };
  if (count <= 4) return { cols: 2, rows: 2 };
  if (count <= 6) return { cols: 3, rows: 2 };
  if (count <= 9) return { cols: 3, rows: 3 };
  return { cols: 4, rows: 3 };
};

interface Cell {
  key: string;
  tile?: MeetingVideoTile;
  participant?: MeetingParticipant;
  screen?: boolean;
}

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
    isCreator,
    endModalOpen,
    ending,
    requestFinish,
    cancelFinish,
    finish,
    toggleMic,
    toggleCam,
    toggleScreen,
    activateSound,
  } = useMeetingOverlay();

  const [pinnedScreenId, setPinnedScreenId] = useState<string | null>(null);

  const attachVideo = useCallback((element: HTMLVideoElement | null) => {
    if (!element || element.srcObject) return;

    const id = element.dataset.tile;
    const track = id ? getVideoTrack(id) : undefined;
    if (track) track.attach(element);
  }, []);

  if (phase === "idle") return null;

  const screenTiles = videoTiles.filter((tile) => tile.kind === "screen");
  const cameraTiles = videoTiles.filter((tile) => tile.kind !== "screen");

  const screenTile =
    screenTiles.find((tile) => tile.id === pinnedScreenId) ??
    screenTiles[screenTiles.length - 1];

  const cells: Cell[] = screenTiles
    .filter((tile) => tile.id !== screenTile?.id)
    .map((tile) => ({ key: tile.id, tile, screen: true }));

  participants.forEach((participant) =>
    cells.push({
      key: participant.identity,
      participant,
      tile: participant.camOn
        ? cameraTiles.find((tile) => tile.identity === participant.identity)
        : undefined,
    }),
  );

  cameraTiles
    .filter(
      (tile) =>
        !participants.some(
          (participant) => participant.identity === tile.identity,
        ),
    )
    .forEach((tile) => cells.push({ key: tile.id, tile }));

  const maxCells = screenTile ? MAX_FILMSTRIP_CELLS : MAX_GRID_CELLS;
  const visibleCells =
    cells.length > maxCells ? cells.slice(0, maxCells - 1) : cells;
  const hiddenCount = cells.length - visibleCells.length;

  const { cols, rows } = gridShape(visibleCells.length + (hiddenCount ? 1 : 0));

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

  const gridStyle = {
    "--cols": String(cols),
    "--rows": String(rows),
    "--ratio": String((cols * 16) / (rows * 9)),
  } as CSSProperties;

  const renderCell = ({ key, tile, participant, screen }: Cell) => {
    if (tile && screen) {
      return (
        <button
          className={style.screenThumb}
          key={key}
          type="button"
          onClick={() => setPinnedScreenId(tile.id)}
          title={`${tile.label} 크게 보기`}
          aria-label={`${tile.label} 크게 보기`}
        >
          <video
            key={tile.id}
            data-tile={tile.id}
            ref={attachVideo}
            autoPlay
            playsInline
            muted
          />
          <span className={style.tileLabel}>{tile.label}</span>
        </button>
      );
    }

    if (tile) {
      return (
        <div className={style.tile} key={key}>
          <video
            className={tile.mirrored ? style.mirrored : undefined}
            key={tile.id}
            data-tile={tile.id}
            ref={attachVideo}
            autoPlay
            playsInline
            muted={participant?.isLocal ?? tile.id.startsWith("local-")}
          />
          <span className={style.tileLabel}>{tile.label}</span>
        </div>
      );
    }

    if (participant) {
      return (
        <MeetingParticipantTile
          key={key}
          participant={participant}
          speaking={speakers.includes(participant.identity)}
        />
      );
    }

    return null;
  };

  return (
    <>
      <section
        className={containerClass}
        style={position}
        aria-label="화상 회의"
      >
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

        <div className={screenTile ? style.stageSpotlight : style.stage}>
          {screenTile && (
            <div className={style.spotlight}>
              <video
                key={screenTile.id}
                data-tile={screenTile.id}
                ref={attachVideo}
                autoPlay
                playsInline
                muted
              />
              <span className={style.tileLabel}>{screenTile.label}</span>
            </div>
          )}

          <div
            className={screenTile ? style.filmstrip : style.grid}
            style={screenTile ? undefined : gridStyle}
          >
            {visibleCells.map(renderCell)}
            {hiddenCount > 0 && (
              <div className={style.overflowCell}>+{hiddenCount}명</div>
            )}
          </div>
        </div>

        <footer className={style.controls}>
          <button
            className={micOn ? style.control : style.controlDanger}
            type="button"
            onClick={toggleMic}
            aria-pressed={micOn}
            aria-label={micOn ? "마이크 끄기" : "마이크 켜기"}
            title={micOn ? "마이크 켜짐" : "음소거됨"}
          >
            {micOn ? <MicOnIcon /> : <MicOffIcon />}
          </button>

          {isImmersive && (
            <>
              <button
                className={camOn ? style.control : style.controlDanger}
                type="button"
                onClick={toggleCam}
                aria-pressed={camOn}
                aria-label={camOn ? "카메라 끄기" : "카메라 켜기"}
                title={camOn ? "카메라 켜짐" : "카메라 꺼짐"}
              >
                {camOn ? <CamOnIcon /> : <CamOffIcon />}
              </button>
              <button
                className={screenOn ? style.controlActive : style.control}
                type="button"
                onClick={toggleScreen}
                aria-pressed={screenOn}
                aria-label={screenOn ? "화면 공유 중지" : "화면 공유"}
                title={screenOn ? "화면 공유 중" : "화면 공유"}
              >
                {screenOn ? <ScreenOnIcon /> : <ScreenOffIcon />}
              </button>
            </>
          )}

          <button
            className={style.leave}
            type="button"
            onClick={leave}
            aria-label="회의에서 나가기"
            title="나가기"
          >
            <LeaveIcon />
          </button>
          {isCreator && (
            <button
              className={style.finish}
              type="button"
              onClick={requestFinish}
            >
              회의 종료
            </button>
          )}
        </footer>
      </section>

      {/* 열 때마다 새로 마운트한다 — 안 그러면 지난 회의의 체크가 남는다 */}
      {endModalOpen && (
        <MeetingEndModal
          isOpen={endModalOpen}
          pending={ending}
          onClose={cancelFinish}
          onEnd={finish}
        />
      )}
    </>
  );
}
