import { apiRequest } from "../../../api/apiClient";

export interface MemberProfileResponse {
  memberId: number;
  name: string;
  email: string;
  profileImageUrl: string | null;
}

let cachedMemberProfile: MemberProfileResponse | null = null;
let pendingMemberProfileRequest: Promise<MemberProfileResponse> | null = null;
let cacheVersion = 0;

export const getCachedMemberProfile = (): MemberProfileResponse | null =>
  cachedMemberProfile;

export const getMemberProfile = (): Promise<MemberProfileResponse> => {
  if (cachedMemberProfile) {
    return Promise.resolve(cachedMemberProfile);
  }

  if (pendingMemberProfileRequest) {
    return pendingMemberProfileRequest;
  }

  const requestVersion = cacheVersion;

  const request = apiRequest<MemberProfileResponse>("/members/me")
    .then((response) => {
      if (requestVersion === cacheVersion) {
        cachedMemberProfile = response;
      }

      return response;
    })
    .finally(() => {
      if (pendingMemberProfileRequest === request) {
        pendingMemberProfileRequest = null;
      }
    });

  pendingMemberProfileRequest = request;
  return request;
};

export const clearMemberProfileCache = () => {
  cacheVersion += 1;
  cachedMemberProfile = null;
  pendingMemberProfileRequest = null;
};

export const deleteMember = (): Promise<void> =>
  apiRequest<void>("/members/me", {
    method: "DELETE",
  }).then(() => {
    clearMemberProfileCache();
  });
