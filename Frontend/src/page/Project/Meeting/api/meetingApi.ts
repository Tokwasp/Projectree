import {
  ApiError,
  type ApiErrorResponse,
  type ApiResponse,
} from "../../../../api/apiClient";
import { useAuthStore } from "../../../../store/authStore";

export interface JoinResponse {
  roomName: string;
  token: string;
  livekitUrl: string;
  created: boolean;
  // 아직 서버가 내려주지 않는다 — 올 때까지 null로 저장한다
  creatorId?: number | null;
}

export interface MeetingOutputOptions {
  generateSummary: boolean;
  generateNodes: boolean;
}

const OPENVIDU_URL = import.meta.env.VITE_OPENVIDU_URL;
const BASE_URL = import.meta.env.VITE_BASE_URL;

const ROOM_NAME_KEY = "meeting-room-name";
const CREATOR_ID_KEY = "meeting-creator-id";

const isErrorResponse = (body: unknown): body is ApiErrorResponse =>
  typeof body === "object" && body !== null && "errorCode" in body;

const unwrap = async <T>(response: Response): Promise<T> => {
  const body: unknown = await response.json().catch(() => null);

  if (!response.ok || !body) {
    if (isErrorResponse(body)) {
      throw new ApiError(body.errorCode, body.errorMessage, body.status);
    }
    throw new ApiError(
      "UNKNOWN_ERROR",
      "요청을 처리하지 못했습니다.",
      response.status,
    );
  }

  return (body as ApiResponse<T>).data;
};
const memberParams = () => {
  const { memberId, name } = useAuthStore.getState();

  if (memberId === null || name === null) {
    throw new ApiError("UNAUTHENTICATED", "다시 로그인해 주세요.", 401);
  }

  return new URLSearchParams({
    memberId: String(memberId),
    memberName: name,
  }).toString();
};

// 종료 버튼은 방을 만든 사람에게만 보여야 해서, 회의 정보를 로컬스토리지에 남긴다
export const getStoredCreatorId = (): number | null => {
  const raw = localStorage.getItem(CREATOR_ID_KEY);
  if (raw === null) return null;

  // 아직 서버가 안 주는 값이라 "null"이 들어있다 — 그때는 방장이 없는 셈이다
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
};

export const join = async (projectId: number): Promise<JoinResponse> => {
  const response = await fetch(
    `${OPENVIDU_URL}/projects/${projectId}/meetings/join?${memberParams()}`,
    {
      method: "POST",
      credentials: "include",
    },
  );

  const info = await unwrap<JoinResponse>(response);

  localStorage.setItem(ROOM_NAME_KEY, info.roomName);
  localStorage.setItem(CREATOR_ID_KEY, JSON.stringify(info.creatorId ?? null));

  return info;
};

export const requestMeetingAnalysis = async (
  projectId: number,
  roomName: string,
  options: MeetingOutputOptions,
): Promise<void> => {
  const response = await fetch(
    `${BASE_URL}/projects/${projectId}/meetings/${encodeURIComponent(
      roomName,
    )}/analysis-request`,
    {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(options),
    },
  );

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);

    if (isErrorResponse(body)) {
      throw new ApiError(body.errorCode, body.errorMessage, body.status);
    }
    throw new ApiError(
      "MEETING_ANALYSIS_REQUEST_FAILED",
      "회의 산출물 생성을 요청하지 못했습니다.",
      response.status,
    );
  }
};

export const endMeeting = async (roomName: string): Promise<void> => {
  const response = await fetch(`${OPENVIDU_URL}/meetings/${roomName}`, {
    method: "DELETE",
    credentials: "include",
  });

  if (!response.ok) {
    throw new ApiError(
      "MEETING_END_FAILED",
      "회의를 종료하지 못했습니다.",
      response.status,
    );
  }
};
