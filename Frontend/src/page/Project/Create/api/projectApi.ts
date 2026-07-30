import { apiRequest } from "../../../../api/apiClient";

export interface ProjectCreateRequest {
  title: string;
  content: string;
  photoUrl: string | null;
  categoryIds: number[];
}

export const createProject = async (
  request: ProjectCreateRequest,
): Promise<number> =>
  apiRequest<number>("/projects", {
    method: "POST",
    body: JSON.stringify(request),
  });
