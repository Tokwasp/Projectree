import { create } from "zustand";

export type MeetingPhase = "idle" | "connecting" | "live";

export interface MeetingParticipant {
  identity: string;
  name: string;
  isLocal: boolean;
  micOn: boolean;
  // 카메라를 끄면 트랙이 unpublish되지 않고 mute만 된다 —
  // 이 값을 안 보면 프레임이 오지 않는 검은 영상을 계속 그리게 된다
  camOn: boolean;
}

export type MeetingTileKind = "camera" | "screen";

export interface MeetingVideoTile {
  id: string;
  label: string;
  mirrored: boolean;
  // 화면공유는 스포트라이트로 크게 띄우고, 카메라는 그리드에 넣는다
  kind: MeetingTileKind;
  // 어느 참가자의 타일인지 — 영상을 끈 참가자를 같은 그리드에 합칠 때 매칭에 쓴다
  identity: string;
}

export interface MeetingMiniPosition {
  x: number;
  y: number;
}

interface MeetingDevices {
  micOn: boolean;
  camOn: boolean;
  screenOn: boolean;
}

interface MeetingSnapshot extends MeetingDevices {
  phase: MeetingPhase;
  projectId: number | null;
  roomName: string | null;
  startedAt: number | null;
  participants: MeetingParticipant[];
  speakers: string[];
  videoTiles: MeetingVideoTile[];
  needSound: boolean;
}

interface MeetingStore extends MeetingSnapshot {
  miniPos: MeetingMiniPosition | null;

  startConnecting: (projectId: number) => void;
  markLive: (roomName: string, devices: MeetingDevices) => void;
  reset: () => void;

  setParticipants: (participants: MeetingParticipant[]) => void;
  setSpeakers: (speakers: string[]) => void;
  setDevices: (devices: Partial<MeetingDevices>) => void;
  setNeedSound: (needSound: boolean) => void;
  setMiniPos: (miniPos: MeetingMiniPosition) => void;
  addVideoTile: (tile: MeetingVideoTile) => void;
  removeVideoTile: (id: string) => void;
}

const initialSnapshot: MeetingSnapshot = {
  phase: "idle",
  projectId: null,
  roomName: null,
  startedAt: null,
  participants: [],
  speakers: [],
  videoTiles: [],
  micOn: false,
  camOn: false,
  screenOn: false,
  needSound: false,
};

export const useMeetingStore = create<MeetingStore>((set) => ({
  ...initialSnapshot,
  miniPos: null,

  startConnecting: (projectId) =>
    set({ ...initialSnapshot, phase: "connecting", projectId }),

  markLive: (roomName, devices) =>
    set({ phase: "live", roomName, startedAt: Date.now(), ...devices }),

  reset: () => set({ ...initialSnapshot }),

  setParticipants: (participants) => set({ participants }),
  setSpeakers: (speakers) => set({ speakers }),
  setDevices: (devices) => set(devices),
  setNeedSound: (needSound) => set({ needSound }),
  setMiniPos: (miniPos) => set({ miniPos }),

  addVideoTile: (tile) =>
    set((state) =>
      state.videoTiles.some((item) => item.id === tile.id)
        ? state
        : { videoTiles: [...state.videoTiles, tile] },
    ),

  removeVideoTile: (id) =>
    set((state) => ({
      videoTiles: state.videoTiles.filter((tile) => tile.id !== id),
    })),
}));
