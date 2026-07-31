import { useCallback, useState } from "react";
import type { CSSProperties } from "react";
import style from "./MeetingOverlay.module.css";
import MeetingParticipantTile from "../MeetingParticipantTile/MeetingParticipantTile";
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

// 스크롤을 만들지 않으려면 칸을 무한정 늘릴 수 없다 — 넘치면 마지막 칸에 "+N"을 쓴다
const MAX_GRID_CELLS = 12;
const MAX_FILMSTRIP_CELLS = 5;

// 열·행을 인원수로 정해야 타일 높이가 남은 공간에서 계산된다
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
  // 크게 보고 있지 않은 다른 사람의 화면공유 — 누르면 스포트라이트와 교체된다
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
    finish,
    toggleMic,
    toggleCam,
    toggleScreen,
    activateSound,
  } = useMeetingOverlay();

  // 크게 볼 공유를 사용자가 고른 값. null이면 가장 최근에 시작된 공유를 쓴다
  const [pinnedScreenId, setPinnedScreenId] = useState<string | null>(null);

  // 타일이 스포트라이트↔그리드로 옮겨 다니면 video 요소가 새로 만들어진다.
  // querySelector로 찾는 effect는 그 시점을 놓치므로 마운트될 때 ref로 붙인다.
  // id는 data-tile에서 읽는다 — 콜백 자체는 하나로 고정해야 리렌더마다 재실행되지 않는다.
  // 이미 붙어 있으면 건너뛴다 — attach는 매번 element.play()를 다시 걸어서,
  // 리렌더마다 호출하면 재생이 끊긴다
  const attachVideo = useCallback((element: HTMLVideoElement | null) => {
    if (!element || element.srcObject) return;

    const id = element.dataset.tile;
    const track = id ? getVideoTrack(id) : undefined;
    if (track) track.attach(element);
  }, []);

  if (phase === "idle") return null;

  const screenTiles = videoTiles.filter((tile) => tile.kind === "screen");
  const cameraTiles = videoTiles.filter((tile) => tile.kind !== "screen");

  // 고른 공유가 끝나면 find가 비므로 자동으로 최근 공유로 되돌아간다
  const screenTile =
    screenTiles.find((tile) => tile.id === pinnedScreenId) ??
    screenTiles[screenTiles.length - 1];

  // 동시에 여러 명이 공유할 수 있다 — 크게 보지 않는 공유는 썸네일로 남겨야 사라지지 않는다.
  // 사람보다 앞에 둬야 칸이 모자랄 때 잘리지 않는다
  const cells: Cell[] = screenTiles
    .filter((tile) => tile.id !== screenTile?.id)
    .map((tile) => ({ key: tile.id, tile, screen: true }));

  // 영상을 켠 사람은 영상으로, 끈 사람은 아바타로 — 같은 그리드에 함께 놓는다.
  // camOn을 봐야 한다: 카메라를 끄면 트랙은 남고 mute만 되므로 타일 존재만으로는 알 수 없다
  participants.forEach((participant) =>
    cells.push({
      key: participant.identity,
      participant,
      tile: participant.camOn
        ? cameraTiles.find((tile) => tile.identity === participant.identity)
        : undefined,
    }),
  );

  // 참가자 목록보다 트랙이 먼저 도착하는 순간이 있어 남는 타일도 실어 준다
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

  // 칸 하나가 16:9가 되도록 그리드 전체가 가져야 할 가로세로비
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

      <div className={screenTile ? style.stageSpotlight : style.stage}>
        {screenTile && (
          <div className={style.spotlight}>
            {/* 공유 화면은 16:9가 아니므로 cover로 자르면 안 된다 */}
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
        <button className={style.finish} type="button" onClick={finish}>
          회의 종료
        </button>
      </footer>
    </section>
  );
}
