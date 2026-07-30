import { useEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { googleLogin, naverLogin } from "../api/authApi";
import {
  getGoogleRedirectUri,
  getNaverRedirectUri,
  popNaverState,
} from "../hooks/useSocialLogin";
import { useAuthStore } from "../../../store/authStore";

export default function OAuthCallback() {
  const { provider } = useParams<{ provider: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const hasRequestedRef = useRef(false);

  useEffect(() => {
    if (hasRequestedRef.current) return;
    hasRequestedRef.current = true;

    const code = searchParams.get("code");
    const errorParam = searchParams.get("error");
    const returnedState = searchParams.get("state");
    const isNaver = provider === "naver";

    // 실패로 끝나더라도 저장된 state를 남겨두지 않는다
    const savedState = isNaver ? popNaverState() : null;

    if (errorParam || !code || (!isNaver && provider !== "google")) {
      navigate("/", { replace: true });
      return;
    }

    // 네이버는 보낸 state가 그대로 돌아왔는지 확인해야 한다 (CSRF 방지)
    if (isNaver && (!returnedState || returnedState !== savedState)) {
      console.error("네이버 로그인 state 검증 실패");
      navigate("/", { replace: true });
      return;
    }

    const request = isNaver ? naverLogin : googleLogin;
    const redirectUri = isNaver
      ? getNaverRedirectUri()
      : getGoogleRedirectUri();
    // 구글에는 state를 보내지 않으므로 항상 undefined가 된다
    const state = returnedState ?? undefined;

    request({ code, redirectUri, state })
      .then((user) => {
        login(user);
        navigate("/home", { replace: true });
      })
      .catch((error) => {
        console.error("소셜 로그인 실패:", error);
        navigate("/", { replace: true });
      });
  }, [provider, searchParams, navigate, login]);

  return (
    <div>
      <span>로그인 처리 중입니다...</span>
    </div>
  );
}
