export interface ProjectCreateRequest {
  title: string;
  content: string;
  photoUrl: string | null;
  categoryIds: number[];
}

interface ApiResponse<T> {
  status: number;
  message: string;
  data: T;
}

interface ApiErrorResponse {
  status: number;
  errorCode: string;
  errorMessage: string;
}

const BASE_URL = import.meta.env.VITE_BASE_URL;

export const createProject = async (
  request: ProjectCreateRequest,
): Promise<number> => {
  const response = await fetch(`${BASE_URL}/projects`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    credentials: "include",
    body: JSON.stringify(request),
  });

  const responseData: ApiResponse<number> | ApiErrorResponse =
    await response.json();

  if (!response.ok) {
    throw new Error(
      "errorMessage" in responseData
        ? responseData.errorMessage
        : responseData.message || "프로젝트 생성에 실패했습니다.",
    );
  }

  return (responseData as ApiResponse<number>).data;
};
