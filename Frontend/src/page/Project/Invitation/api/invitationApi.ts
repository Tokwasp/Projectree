import { apiRequest } from "../../../../api/apiClient";

export type InvitationStatus =
  | "PENDING"
  | "ACCEPTED"
  | "REJECTED"
  | "CANCELED";

export interface InvitationLandingResponse {
  projectTitle: string;
  inviterName: string;
  status: InvitationStatus;
  expired: boolean;
}

export interface InvitationAcceptResponse {
  projectId: number;
}

export const getInvitation = (
  token: string,
): Promise<InvitationLandingResponse> =>
  apiRequest<InvitationLandingResponse>(
    `/invitations/${encodeURIComponent(token)}`,
  );

export const acceptInvitation = (
  token: string,
): Promise<InvitationAcceptResponse> =>
  apiRequest<InvitationAcceptResponse>(
    `/invitations/${encodeURIComponent(token)}/accept`,
    {
      method: "POST",
    },
  );

export const rejectInvitation = (
  token: string,
): Promise<void> =>
  apiRequest<void>(
    `/invitations/${encodeURIComponent(token)}/reject`,
    {
      method: "POST",
    },
  );