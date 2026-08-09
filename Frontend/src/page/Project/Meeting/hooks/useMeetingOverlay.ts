import { useEffect, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import {
  endMeeting,
  getStoredCreatorId,
  requestMeetingAnalysis,
  type MeetingOutputOptions,
} from "../api/meetingApi";
import { apiErrorMessage } from "../../../../api/apiClient";
import { useAuthStore } from "../../../../store/authStore";
import { useMeetingStore } from "../../../../store/meetingStore";
import { toast } from "../../../../store/toastStore";
import {
  disconnectMeeting,
  enableSound,
  toggleCamera,
  toggleMicrophone,
  toggleScreenShare,
} from "../../../../utils/meetingSession";

const MINI_WIDTH = 320;
const MINI_HEIGHT = 100;
const MINI_MARGIN = 24;
const DRAG_THRESHOLD = 4;

interface DragState {
  pointerId: number;
  offsetX: number;
  offsetY: number;
  startX: number;
  startY: number;
  moved: boolean;
}

const clampPosition = (x: number, y: number) => ({
  x: Math.min(
    Math.max(x, MINI_MARGIN),
    window.innerWidth - MINI_WIDTH - MINI_MARGIN,
  ),
  y: Math.min(
    Math.max(y, MINI_MARGIN),
    window.innerHeight - MINI_HEIGHT - MINI_MARGIN,
  ),
});

export const formatElapsed = (seconds: number) => {
  const minutes = String(Math.floor(seconds / 60)).padStart(2, "0");
  const rest = String(seconds % 60).padStart(2, "0");
  return `${minutes}:${rest}`;
};

export const useMeetingOverlay = () => {
  const phase = useMeetingStore((state) => state.phase);
  const projectId = useMeetingStore((state) => state.projectId);
  const roomName = useMeetingStore((state) => state.roomName);
  const startedAt = useMeetingStore((state) => state.startedAt);
  const miniPos = useMeetingStore((state) => state.miniPos);
  const setMiniPos = useMeetingStore((state) => state.setMiniPos);
  const memberId = useAuthStore((state) => state.memberId);

  const location = useLocation();
  const navigate = useNavigate();
  const [elapsed, setElapsed] = useState(0);
  const [endModalOpen, setEndModalOpen] = useState(false);
  const [ending, setEnding] = useState(false);
  const dragRef = useRef<DragState | null>(null);

  const meetingPath = `/projects/${projectId}/meeting`;
  const isImmersive = location.pathname === meetingPath;

  const creatorId = getStoredCreatorId();
  const isCreator =
    memberId !== null && (creatorId === null || memberId === creatorId);

  useEffect(() => {
    if (phase !== "live" || !startedAt) return;

    const update = () =>
      setElapsed(Math.floor((Date.now() - startedAt) / 1000));

    update();
    const timer = setInterval(update, 1000);
    return () => clearInterval(timer);
  }, [phase, startedAt]);

  useEffect(() => {
    if (isImmersive || miniPos) return;

    setMiniPos(
      clampPosition(
        window.innerWidth - MINI_WIDTH - MINI_MARGIN,
        window.innerHeight - MINI_HEIGHT - MINI_MARGIN,
      ),
    );
  }, [isImmersive, miniPos, setMiniPos]);

  useEffect(() => {
    const handleResize = () => {
      const current = useMeetingStore.getState().miniPos;
      if (current) setMiniPos(clampPosition(current.x, current.y));
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [setMiniPos]);

  useEffect(() => {
    if (phase === "idle") return;

    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [phase]);

  const handlePointerDown = (event: ReactPointerEvent<HTMLElement>) => {
    if (isImmersive) return;

    const bounds = event.currentTarget.getBoundingClientRect();
    dragRef.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - bounds.left,
      offsetY: event.clientY - bounds.top,
      startX: event.clientX,
      startY: event.clientY,
      moved: false,
    };
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;

    if (
      Math.abs(event.clientX - drag.startX) > DRAG_THRESHOLD ||
      Math.abs(event.clientY - drag.startY) > DRAG_THRESHOLD
    ) {
      drag.moved = true;
    }

    setMiniPos(
      clampPosition(event.clientX - drag.offsetX, event.clientY - drag.offsetY),
    );
  };

  const handlePointerUp = (event: ReactPointerEvent<HTMLElement>) => {
    const drag = dragRef.current;
    dragRef.current = null;
    if (!drag) return;

    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }

    if (!drag.moved) navigate(meetingPath);
  };

  const expand = () => navigate(meetingPath);

  const leave = async () => {
    await disconnectMeeting();
    navigate(`/projects/${projectId}`);
  };

  const requestFinish = () => setEndModalOpen(true);
  const cancelFinish = () => setEndModalOpen(false);

  const finish = async (options: MeetingOutputOptions) => {
    setEnding(true);

    if (roomName) {
      try {
        if (projectId !== null) {
          await requestMeetingAnalysis(projectId, roomName, options);
        }
        await endMeeting(roomName);
      } catch (caught) {
        console.error("회의 종료 요청 실패:", caught);
        toast.error(apiErrorMessage(caught, "회의를 종료하지 못했습니다."));
        setEnding(false);
        return;
      }
    }

    setEnding(false);
    setEndModalOpen(false);
    await disconnectMeeting();
    navigate(`/projects/${projectId}`);

    toast.success(
      options.generateSummary || options.generateNodes
        ? "회의를 종료했습니다. 선택한 산출물은 잠시 후 생성됩니다."
        : "회의를 종료했습니다.",
    );
  };

  return {
    isImmersive,
    elapsed,
    miniPos,
    isCreator,
    endModalOpen,
    ending,
    handlePointerDown,
    handlePointerMove,
    handlePointerUp,
    expand,
    leave,
    requestFinish,
    cancelFinish,
    finish,
    toggleMic: toggleMicrophone,
    toggleCam: toggleCamera,
    toggleScreen: toggleScreenShare,
    activateSound: enableSound,
  };
};
