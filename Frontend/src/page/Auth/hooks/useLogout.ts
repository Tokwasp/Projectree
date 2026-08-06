import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../../api/apiClient";
import { useAuthStore } from "../../../store/authStore";
import { logout as requestLogout } from "../api/authApi";

export default function useLogout() {
  const navigate = useNavigate();
  const clearLoginState = useAuthStore((state) => state.logout);
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const finishLogout = () => {
    clearLoginState();
    navigate("/", { replace: true });
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

      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "로그아웃에 실패했습니다.";

      setError(message);
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