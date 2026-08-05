import { apiRequest } from "../../../api/apiClient";

export type SocialProvider = "google" | "naver";

export interface SocialLoginRequest {
  code: string;
  redirectUri: string;
  state?: string;
}

// 서버는 회원 식별자를 id로 내려준다 (네이버 응답에는 아직 없다)
interface SocialLoginResponse {
  id?: number;
  name: string;
  imageUrl: string;
}

export interface LoginUser {
  memberId: number | null;
  name: string;
  imageUrl: string;
}

const postSocialLogin = async (
  provider: SocialProvider,
  payload: SocialLoginRequest,
): Promise<LoginUser> => {
  const { id, name, imageUrl } = await apiRequest<SocialLoginResponse>(
    `/auth/${provider}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );

  return { memberId: id ?? null, name, imageUrl };
};

export const naverLogin = (payload: SocialLoginRequest) =>
  postSocialLogin("naver", payload);

export const googleLogin = (payload: SocialLoginRequest) =>
  postSocialLogin("google", payload);
