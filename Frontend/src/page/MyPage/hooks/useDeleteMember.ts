import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../../api/apiClient";
import { useAuthStore } from "../../../store/authStore";
import { toast } from "../../../store/toastStore";
import { deleteMember as requestDeleteMember } from "../api/memberProfileApi";

export default function useDeleteMember() {
  const navigate = useNavigate();
  const clearLoginState = useAuthStore((state) => state.logout);
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deleteMember = async () => {
    if (isDeleting) {
      return false;
    }

    setIsDeleting(true);
    setError(null);

    try {
      await requestDeleteMember();
      clearLoginState();
      navigate("/", { replace: true });
      // 탈퇴 실패는 모달에 그려지지만, 성공하면 모달째 사라져서 알릴 곳이 없다
      toast.success("회원 탈퇴가 완료되었습니다.");
      return true;
    } catch (caughtError) {
      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "회원 탈퇴에 실패했습니다.";

      setError(message);
      return false;
    } finally {
      setIsDeleting(false);
    }
  };

  const clearError = () => {
    setError(null);
  };

  return {
    deleteMember,
    isDeleting,
    error,
    clearError,
  };
}
