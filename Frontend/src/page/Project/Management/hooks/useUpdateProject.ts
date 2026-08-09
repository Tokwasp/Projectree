import { useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import { toast } from "../../../../store/toastStore";
import { updateProjectInListCache } from "../../List/api/projectListApi";
import {
  updateProjectContent,
  updateProjectImage,
  updateProjectTitle,
} from "../api/projectManagementApi";

export default function useUpdateProject() {
  const [isUpdating, setIsUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const executeUpdate = async (
    request: () => Promise<void>,
    successMessage: string,
    onSuccess?: () => void,
  ): Promise<boolean> => {
    setIsUpdating(true);
    setError(null);

    try {
      await request();
      onSuccess?.();
      toast.success(successMessage);
      return true;
    } catch (caughtError) {
      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "프로젝트 정보 수정에 실패했습니다.";

      setError(message);
      return false;
    } finally {
      setIsUpdating(false);
    }
  };

  const updateTitle = (projectId: number, title: string) =>
    executeUpdate(
      () => updateProjectTitle(projectId, title),
      "프로젝트 이름을 변경했습니다.",
      () => updateProjectInListCache(projectId, { title }),
    );

  const updateContent = (projectId: number, content: string) =>
    executeUpdate(
      () => updateProjectContent(projectId, content),
      "프로젝트 설명을 변경했습니다.",
    );

  const updateImage = (projectId: number, imageURL: string) =>
    executeUpdate(
      () => updateProjectImage(projectId, imageURL),
      "프로젝트 사진을 변경했습니다.",
      () => updateProjectInListCache(projectId, { photoUrl: imageURL }),
    );

  return {
    updateTitle,
    updateContent,
    updateImage,
    isUpdating,
    error,
    clearError: () => setError(null),
  };
}
