import { apiRequest } from "../../../api/apiClient";

export interface MemberProfileResponse {
  memberId: number;
  name: string;
  email: string;
  profileImageUrl: string | null;
}

export const getMemberProfile = (): Promise<MemberProfileResponse> =>
  apiRequest<MemberProfileResponse>("/members/me");

export const deleteMember = (): Promise<void> =>
  apiRequest<void>("/members/me", {
    method: "DELETE",
  });
