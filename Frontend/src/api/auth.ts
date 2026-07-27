export type SocialProvider = "google" | "naver";

export interface SocialLoginRequest {
  code: string;
  redirectUri: string;
  // 네이버는 CSRF 방지용 state를 함께 검증한다
  state?: string;
}

export interface SocialLoginResponse {
  accessToken: string;
  name: string;
  profileImage: string;
  message?: string;
}

const BASE_URL = import.meta.env.VITE_BASE_URL;

const postSocialLogin = async (
  provider: SocialProvider,
  payload: SocialLoginRequest,
): Promise<SocialLoginResponse> => {
  const response = await fetch(`${BASE_URL}/auth/${provider}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error);
  }

  return response.json();
};

// 인가 코드를 백엔드에 넘겨 accessToken을 받아온다
export const naverLogin = (payload: SocialLoginRequest) =>
  postSocialLogin("naver", payload);

export const googleLogin = (payload: SocialLoginRequest) =>
  postSocialLogin("google", payload);
