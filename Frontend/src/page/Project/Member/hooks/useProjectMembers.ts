import { useEffect, useState } from "react";
import { apiErrorMessage } from "../../../../api/apiClient";
import {
  getProjectMembers,
  type ProjectMemberResponse,
} from "../api/projectMemberApi";

export default function useProjectMembers(projectId: number | null) {
  const [members, setMembers] = useState<ProjectMemberResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (projectId === null) {
      return;
    }

    let isCancelled = false;

    const fetchProjectMembers = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await getProjectMembers(projectId);

        if (!isCancelled) {
          setMembers(response.members);
        }
      } catch (caughtError) {
        if (!isCancelled) {
          setError(
            apiErrorMessage(caughtError, "팀원 목록을 불러오지 못했습니다."),
          );
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void fetchProjectMembers();

    return () => {
      isCancelled = true;
    };
  }, [projectId]);

  return {
    members: projectId === null ? [] : members,
    isLoading: projectId === null ? false : isLoading,
    error:
      projectId === null
        ? "올바르지 않은 프로젝트입니다."
        : error,
  };
}
