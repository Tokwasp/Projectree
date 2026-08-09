import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, apiErrorMessage } from "../../../api/apiClient";
import { useAuthStore } from "../../../store/authStore";
import { toast } from "../../../store/toastStore";
import { logout as requestLogout } from "../api/authApi";

export default function useLogout() {
  const navigate = useNavigate();
  const clearLoginState = useAuthStore((state) => state.logout);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const finishLogout = () => {
    clearLoginState();
    navigate("/", { replace: true });
    // 랜딩으로 튕겨서 눌렀던 화면이 사라진다 — 실패는 인라인에 남지만 성공은 흔적이 없다
    toast.success("로그아웃했습니다.");
  };

  const logout = async () => {
    if (isLoggingOut) {
      return;
    }

    setIsLoggingOut(true);
    setError(null);

    try {
      await requestLogout();
      finishLogout();
    } catch (caughtError) {
      if (caughtError instanceof ApiError && caughtError.status === 401) {
        finishLogout();
        return;
      }

      setError(apiErrorMessage(caughtError, "로그아웃에 실패했습니다."));
    } finally {
      setIsLoggingOut(false);
    }
  };

  return {
    logout,
    isLoggingOut,
    error,
  };
}