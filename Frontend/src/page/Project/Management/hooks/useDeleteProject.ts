import { useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import { toast } from "../../../../store/toastStore";
import { clearProjectListCache } from "../../List/api/projectListApi";
import { deleteProject as requestDeleteProject } from "../api/projectManagementApi";

export default function useDeleteProject() {
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deleteProject = async (projectId: number): Promise<boolean> => {
    setIsDeleting(true);
    setError(null);

    try {
      await requestDeleteProject(projectId);
      clearProjectListCache();
      toast.success("프로젝트를 삭제했습니다.");
      return true;
    } catch (caughtError) {
      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "프로젝트 삭제에 실패했습니다.";

      setError(message);
      return false;
    } finally {
      setIsDeleting(false);
    }
  };

  return {
    deleteProject,
    isDeleting,
    error,
    clearError: () => setError(null),
  };
}
