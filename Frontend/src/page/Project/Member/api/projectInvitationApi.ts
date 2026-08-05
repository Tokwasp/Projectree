import { apiRequest } from "../../../../api/apiClient";

export interface MemberSearchResponse {
  memberId: number;
  name: string;
  email: string;
}

export type InviteResult =
  | "INVITED"
  | "RESENT"
  | "MEMBER_NOT_FOUND"
  | "ALREADY_MEMBER"
  | "SELF_INVITE"
  | "COOLDOWN";

export interface InviteTargetResponse {
  inviteeMemberId: number;
  result: InviteResult;
}

export interface InviteResultsResponse {
  results: InviteTargetResponse[];
}

export interface InvitationCreateRequest {
  inviteeMemberIds: number[];
}

export const findMemberByEmail = (
  email: string,
): Promise<MemberSearchResponse> =>
  apiRequest<MemberSearchResponse>(
    `/members?email=${encodeURIComponent(email)}`,
  );

export const inviteProjectMembers = (
  projectId: number,
  request: InvitationCreateRequest,
): Promise<InviteResultsResponse> =>
  apiRequest<InviteResultsResponse>(
    `/projects/${projectId}/invitations`,
    {
      method: "POST",
      body: JSON.stringify(request),
    },
  );