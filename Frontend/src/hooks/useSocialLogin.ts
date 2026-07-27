const NAVER_CLIENT_ID = import.meta.env.VITE_NAVER_CLIENT_ID;
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

const NAVER_STATE_KEY = "naver_oauth_state";

export const getNaverRedirectUri = () =>
  `${window.location.origin}/auth/naver/callback`;

export const getGoogleRedirectUri = () =>
  `${window.location.origin}/auth/google/callback`;

export const popNaverState = () => {
  const state = sessionStorage.getItem(NAVER_STATE_KEY);
  sessionStorage.removeItem(NAVER_STATE_KEY);
  return state;
};

export function useSocialLogin() {
  const loginWithNaver = () => {
    const state = crypto.randomUUID();
    sessionStorage.setItem(NAVER_STATE_KEY, state);

    const params = new URLSearchParams({
      client_id: NAVER_CLIENT_ID,
      redirect_uri: getNaverRedirectUri(),
      response_type: "code",
      state,
    });
    window.location.href = `https://nid.naver.com/oauth2.0/authorize?${params.toString()}`;
  };

  const loginWithGoogle = () => {
    const params = new URLSearchParams({
      client_id: GOOGLE_CLIENT_ID,
      redirect_uri: getGoogleRedirectUri(),
      response_type: "code",
      scope: "openid email profile",
      access_type: "offline",
      prompt: "consent",
    });
    window.location.href = `https://accounts.google.com/o/oauth2/v2/auth?${params.toString()}`;
  };

  return { loginWithNaver, loginWithGoogle };
}
