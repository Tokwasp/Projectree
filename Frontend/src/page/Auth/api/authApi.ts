import { apiRequest } from "../../../api/apiClient";

export type SocialProvider = "google" | "naver";

export interface SocialLoginRequest {
  code: string;
  redirectUri: string;
  state?: string;
}

export interface LoginUser {
  memberId: number;
  name: string;
  imageUrl: string;
}

const postSocialLogin = (
  provider: SocialProvider,
  payload: SocialLoginRequest,
) =>
  apiRequest<LoginUser>(`/auth/${provider}`, {
    method: "POST",
    body: JSON.stringify(payload),
  });

export const naverLogin = (payload: SocialLoginRequest) =>
  postSocialLogin("naver", payload);

export const googleLogin = (payload: SocialLoginRequest) =>
  postSocialLogin("google", payload);
