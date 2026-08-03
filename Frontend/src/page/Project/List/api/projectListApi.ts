import { apiRequest } from "../../../../api/apiClient";

export interface ProjectListItemResponse {
  projectId: number;
  title: string;
  photoUrl: string | null;
  memberCnt: number;
}

export interface ProjectListResponse {
  projects: ProjectListItemResponse[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}

export const getProjectList = (
  page: number,
  size: number,
): Promise<ProjectListResponse> =>
  apiRequest<ProjectListResponse>(
    `/projects?page=${page}&size=${size}`,
  );
