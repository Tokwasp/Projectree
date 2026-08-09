const BASE_URL = import.meta.env.VITE_BASE_URL;

export interface ApiResponse<T> {
  data: T;
  message: string;
  status: number;
}

export interface ApiErrorResponse {
  errorCode: string;
  errorMessage: string;
  status: number;
}

export class ApiError extends Error {
  errorCode: string;
  status: number;

  constructor(errorCode: string, errorMessage: string, status: number) {
    super(errorMessage);
    this.name = "ApiError";
    this.errorCode = errorCode;
    this.status = status;
  }
}

const isErrorResponse = (body: unknown): body is ApiErrorResponse =>
  typeof body === "object" && body !== null && "errorCode" in body;

/**
 * 실패 사유는 서버가 가장 정확히 안다 — 응답을 받았다면 서버 메시지를 그대로 띄운다.
 * fallback은 네트워크가 끊겨 서버에 닿지도 못한 경우에만 쓰인다.
 */
export const apiErrorMessage = (caught: unknown, fallback: string): string =>
  caught instanceof ApiError ? caught.message : fallback;

export const apiRequest = async <T>(
  path: string,
  init: RequestInit = {},
): Promise<T> => {
  const response = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (response.status === 204 && response.ok) {
    return undefined as T;
  }

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
