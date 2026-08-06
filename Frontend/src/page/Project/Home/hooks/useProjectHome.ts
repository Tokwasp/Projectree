import { useEffect, useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import {
  getProjectHome,
  type ProjectHomeResponse,
} from "../api/projectHomeApi";

export default function useProjectHome(projectId: number | null) {
  const [data, setData] = useState<ProjectHomeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (projectId === null) {
      return;
    }

    let isCancelled = false;

    const fetchProjectHome = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await getProjectHome(projectId);

        if (!isCancelled) {
          setData(response);
        }
      } catch (caughtError) {
        const message =
          caughtError instanceof ApiError
            ? caughtError.message
            : "프로젝트 홈을 불러오지 못했습니다.";

        if (!isCancelled) {
          setData(null);
          setError(message);
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void fetchProjectHome();

    return () => {
      isCancelled = true;
    };
  }, [projectId]);

  return {
    data: projectId === null ? null : data,
    isLoading: projectId === null ? false : isLoading,
    error:
      projectId === null
        ? "올바르지 않은 프로젝트입니다."
        : error,
  };
}
