import { useState } from "react";
import {
  createProject as requestCreateProject,
  type ProjectCreateRequest,
} from "../api/projectApi";
import { ApiError } from "../../../../api/apiClient";

export default function useCreateProject() {
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createProject = async (
    request: ProjectCreateRequest,
  ): Promise<number | null> => {
    setIsCreating(true);
    setError(null);

    try {
      return await requestCreateProject(request);
    } catch (caughtError) {
      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "프로젝트 생성에 실패했습니다.";

      setError(message);
      return null;
    } finally {
      setIsCreating(false);
    }
  };

  return {
    createProject,
    isCreating,
    error,
  };
}
