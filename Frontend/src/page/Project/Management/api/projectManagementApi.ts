import { apiRequest } from "../../../../api/apiClient";

export const deleteProject = (projectId: number): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}`, {
    method: "DELETE",
  });

export const leaveProject = (projectId: number): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}/members/me`, {
    method: "DELETE",
  });
