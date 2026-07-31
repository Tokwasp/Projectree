import { create } from "zustand";

export type MeetingPhase = "idle" | "connecting" | "live";

export interface MeetingParticipant {
  identity: string;
  name: string;
  isLocal: boolean;
  micOn: boolean;
}

export interface MeetingVideoTile {
  id: string;
  label: string;
  mirrored: boolean;
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
