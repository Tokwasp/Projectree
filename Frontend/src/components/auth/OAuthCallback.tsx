import { useEffect, useRef } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { googleLogin, naverLogin } from "../../api/auth";
import {
  getGoogleRedirectUri,
  getNaverRedirectUri,
  popNaverState,
} from "../../hooks/useSocialLogin";

export default function OAuthCallback() {
  const { provider } = useParams<{ provider: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const hasRequestedRef = useRef(false);

  useEffect(() => {
    if (hasRequestedRef.current) return;
    hasRequestedRef.current = true;

    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const errorParam = searchParams.get("error");

    if (
      errorParam ||
      !code ||
      (provider !== "naver" && provider !== "google")
    ) {
      navigate("/", { replace: true });
      return;
    }

    let request;

    if (provider === "naver") {
      const savedState = popNaverState();
      if (!state || state !== savedState) {
        console.error("state 불일치", { state, savedState });
        navigate("/", { replace: true });
        return;
      }
      request = naverLogin({ code, state, redirectUri: getNaverRedirectUri() });
    } else {
      request = googleLogin({ code, redirectUri: getGoogleRedirectUri() });
    }

    request
      .then((data) => {
        console.log("로그인 응답:", data);
        navigate("/home", { replace: true });
      })
      .catch((error) => {
        console.error("소셜 로그인 실패:", error);
        navigate("/", { replace: true });
      });
  }, [provider, searchParams, navigate]);

  return (
    <div>
      <span className="trip-body1">로그인 처리 중입니다...</span>
    </div>
  );
}
