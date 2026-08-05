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
}

const OPENVIDU_URL = import.meta.env.VITE_OPENVIDU_URL;

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

export const join = async (projectId: number): Promise<JoinResponse> => {
  const response = await fetch(
    `${OPENVIDU_URL}/projects/${projectId}/meetings/join?${memberParams()}`,
    {
      method: "POST",
      credentials: "include",
    },
  );

  return unwrap<JoinResponse>(response);
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
