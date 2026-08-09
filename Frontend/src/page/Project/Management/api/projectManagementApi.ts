import { apiRequest } from "../../../../api/apiClient";

export const updateProjectImage = (
  projectId: number,
  imageURL: string,
): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}/image`, {
    method: "PUT",
    body: JSON.stringify({ imageURL }),
  });

export const updateProjectTitle = (
  projectId: number,
  title: string,
): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}/title`, {
    method: "PUT",
    body: JSON.stringify({ title }),
  });

export const updateProjectContent = (
  projectId: number,
  content: string,
): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}/content`, {
    method: "PUT",
    body: JSON.stringify({ content }),
  });

export const deleteProject = (projectId: number): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}`, {
    method: "DELETE",
  });

export const leaveProject = (projectId: number): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}/members/me`, {
    method: "DELETE",
  });
