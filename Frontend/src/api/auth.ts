export type SocialProvider = "google" | "naver";

export interface SocialLoginRequest {
  code: string;
  redirectUri: string;
  state?: string;
}

export interface SocialLoginResponse {
  name: string;
  imageUrl: string;
  message?: string;
}

const BASE_URL = import.meta.env.VITE_BASE_URL;

const postSocialLogin = async (
  provider: SocialProvider,
  payload: SocialLoginRequest,
): Promise<SocialLoginResponse> => {
  const response = await fetch(`${BASE_URL}/auth/${provider}`, {
    method: "POST",
    credentials: "include",
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

export const naverLogin = (payload: SocialLoginRequest) =>
  postSocialLogin("naver", payload);

export const googleLogin = (payload: SocialLoginRequest) =>
  postSocialLogin("google", payload);
