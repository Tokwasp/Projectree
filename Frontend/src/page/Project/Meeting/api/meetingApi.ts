import { ApiError, apiRequest } from "../../../../api/apiClient";

const BASE_URL = import.meta.env.VITE_BASE_URL;

export interface JoinResponse {
  roomName: string;
  token: string;
  livekitUrl: string;
  created: boolean;
}

export const join = (projectId: number): Promise<JoinResponse> =>
  apiRequest<JoinResponse>(`/projects/${projectId}/meetings/join`, {
    method: "POST",
  });

export const endMeeting = async (roomName: string): Promise<void> => {
  const response = await fetch(`${BASE_URL}/meetings/${roomName}`, {
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
