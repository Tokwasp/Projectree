import {
  ApiError,
  type ApiErrorResponse,
  type ApiResponse,
} from "../../../../api/apiClient";

export interface JoinResponse {
  roomName: string;
  token: string;
  livekitUrl: string;
  created: boolean;
}

/* ─────────────────── 배포용 원본 (세션 인증 필요) ───────────────────
   테스트가 끝나면 아래 "테스트용" 블록을 지우고 이 코드를 되살릴 것.
   되돌릴 때 함께 원복해야 하는 것:
   - 이 파일 상단 import 를 `import { ApiError, apiRequest } from "../../../../api/apiClient";` 로
   - 이 파일 상단에 `const BASE_URL = import.meta.env.VITE_BASE_URL;` 복원
   - useMeetingPrejoin.ts  join(projectId)
   - useMeetingOverlay.ts  endMeeting(roomName)

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

─────────────────── 배포용 원본 끝 ─────────────────── */

// ═════════════════ 테스트용 (dev-auth-bypass) — 배포 전 반드시 제거 ═════════════════
// 세션이 없는 환경에서 붙기 위해 memberId/memberName을 쿼리파라미터로 넘긴다.
// 실제 운영은 세션에서 읽으므로 이 코드로 배포하면 안 된다.
// 절대 URL이라 vite 프록시(/api)를 타지 않고 브라우저가 직접 크로스 오리진 요청을 보낸다.
const TEST_API_BASE = "https://i15d205.p.ssafy.io/api";
const TEST_PROJECT_ID = 12;
const TEST_MEMBER_ID = 1;
const TEST_MEMBER_NAME = "안현석";
const TEST_ROOM_NAME = "5";

// 한 대에서 2인 회의를 테스트하려고 창마다 다른 사용자로 붙을 때 쓴다.
// 쿼리가 없으면 위 하드코딩 값을 그대로 쓰므로 평소 동작은 바뀌지 않는다.
//   1번 창: /projects/1/meeting
//   2번 창: /projects/1/meeting?memberId=2&memberName=tester2
// LiveKit은 같은 identity가 다시 들어오면 기존 참가자를 끊는다 —
// 두 번째 창은 반드시 memberId를 다르게 줘야 한 명이 튕기지 않는다.
const testParam = (key: string, fallback: string) =>
  new URLSearchParams(window.location.search).get(key) || fallback;

// apiRequest는 BASE_URL을 앞에 붙이므로 절대 URL에는 쓸 수 없다 — 언래핑만 그대로 옮겨온다
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

export const join = async (): Promise<JoinResponse> => {
  const projectId = testParam("projectId", String(TEST_PROJECT_ID));
  const query = new URLSearchParams({
    memberId: testParam("memberId", String(TEST_MEMBER_ID)),
    memberName: testParam("memberName", TEST_MEMBER_NAME),
  }).toString();

  // credentials:"include"로 SESSION 쿠키를 함께 보낸다
  const response = await fetch(
    `${TEST_API_BASE}/projects/${projectId}/meetings/join?${query}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
    },
  );

  return unwrap<JoinResponse>(response);
};

// 회의 종료(방장) — roomName으로 deleteRoom. Redis는 room_finished 웹훅이 닫는다.
export const endMeeting = async (): Promise<void> => {
  const roomName = testParam("roomName", TEST_ROOM_NAME);
  const response = await fetch(`${TEST_API_BASE}/meetings/${roomName}`, {
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
