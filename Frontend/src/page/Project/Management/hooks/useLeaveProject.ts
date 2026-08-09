import { useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import { toast } from "../../../../store/toastStore";
import { clearProjectListCache } from "../../List/api/projectListApi";
import { leaveProject as requestLeaveProject } from "../api/projectManagementApi";

export default function useLeaveProject() {
  const [isLeaving, setIsLeaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const leaveProject = async (projectId: number): Promise<boolean> => {
    setIsLeaving(true);
    setError(null);

    try {
      await requestLeaveProject(projectId);
      clearProjectListCache();
      toast.success("프로젝트에서 나갔습니다.");
      return true;
    } catch (caughtError) {
      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "프로젝트 나가기에 실패했습니다.";

      setError(message);
      return false;
    } finally {
      setIsLeaving(false);
    }
  };

  return {
    leaveProject,
    isLeaving,
    error,
    clearError: () => setError(null),
  };
}
