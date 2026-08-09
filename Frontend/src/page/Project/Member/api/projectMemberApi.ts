import { apiRequest } from "../../../../api/apiClient";

export type ProjectRole = "OWNER" | "MEMBER";

export interface ProjectMemberResponse {
  memberId: number;
  name: string;
  email: string;
  role: ProjectRole;
  joinedAt: string;
}

export interface ProjectMemberListResponse {
  members: ProjectMemberResponse[];
}

export const getProjectMembers = (
  projectId: number,
): Promise<ProjectMemberListResponse> =>
  apiRequest<ProjectMemberListResponse>(
    `/projects/${projectId}/members`,
  );