import { useEffect, useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import type { ProjectSummary } from "../../../../types/Project";
import {
  getCachedProjectList,
  getProjectList,
  prefetchProjectList,
  subscribeProjectList,
  type ProjectListResponse,
} from "../api/projectListApi";

export default function useProjectList(page: number, size: number) {
  const [projectList, setProjectList] =
    useState<ProjectListResponse | null>(() =>
      getCachedProjectList(page, size),
    );
  const [isLoading, setIsLoading] = useState(
    () => getCachedProjectList(page, size) === null,
  );
  const [error, setError] = useState<string | null>(null);

  const cachedProjectList = getCachedProjectList(page, size);
  const currentProjectList = cachedProjectList ?? projectList;

  useEffect(
    () =>
      subscribeProjectList(() => {
        const updatedProjectList = getCachedProjectList(page, size);

        if (updatedProjectList) {
          setProjectList(updatedProjectList);
        }
      }),
    [page, size],
  );

  useEffect(() => {
    let isActive = true;

    const fetchProjectList = async () => {
      const cachedResponse = getCachedProjectList(page, size);

      setIsLoading(cachedResponse === null);
      setError(null);

      try {
        const response = await getProjectList(page, size);

        if (isActive) {
          setProjectList(response);
        }

        const nextPage = response.page + 1;

        if (nextPage < response.totalPages) {
          void prefetchProjectList(nextPage, size).catch(
            () => undefined,
          );
        }
      } catch (caughtError) {
        const message =
          caughtError instanceof ApiError
            ? caughtError.message
            : "프로젝트 목록 조회에 실패했습니다.";

        if (isActive) {
          setError(message);
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    };

    fetchProjectList();

    return () => {
      isActive = false;
    };
  }, [page, size]);

  const projects: ProjectSummary[] =
    currentProjectList?.projects.map((project) => ({
      projectId: project.projectId,
      title: project.title,
      memberCount: project.memberCnt,
      thumbnailUrl: project.photoUrl ?? undefined,
    })) ?? [];

  return {
    projects,
    page: currentProjectList?.page ?? page,
    totalElements: currentProjectList?.totalElements ?? 0,
    totalPages: currentProjectList?.totalPages ?? 0,
    isLoading: cachedProjectList ? false : isLoading,
    error: cachedProjectList ? null : error,
  };
}
