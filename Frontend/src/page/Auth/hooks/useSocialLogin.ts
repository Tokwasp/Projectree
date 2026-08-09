const NAVER_CLIENT_ID = import.meta.env.VITE_NAVER_CLIENT_ID;
const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;

const NAVER_STATE_KEY = "naver_oauth_state";
const LOGIN_REDIRECT_PATH_KEY = "login_redirect_path";

const isSafeRedirectPath = (path: string) =>
  path.startsWith("/") && !path.startsWith("//") && !path.includes("\\");

export const setLoginRedirectPath = (path: string) => {
  if (isSafeRedirectPath(path)) {
    sessionStorage.setItem(LOGIN_REDIRECT_PATH_KEY, path);
  }
};

export const popLoginRedirectPath = () => {
  const path = sessionStorage.getItem(LOGIN_REDIRECT_PATH_KEY);
  sessionStorage.removeItem(LOGIN_REDIRECT_PATH_KEY);

  return path && isSafeRedirectPath(path) ? path : null;
};

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
      state: state,
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
