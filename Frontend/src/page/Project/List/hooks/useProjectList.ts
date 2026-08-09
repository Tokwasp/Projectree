import { useEffect, useState } from "react";
import { apiErrorMessage } from "../../../../api/apiClient";
import type { ProjectSummary } from "../../../../types/Project";
import {
  getCachedProjectList,
  getProjectList,
  prefetchProjectList,
  subscribeProjectList,
  type ProjectListResponse,
} from "../api/projectListApi";

export default function useProjectList(
  page: number,
  size: number,
  keyword = "",
) {
  const [projectList, setProjectList] =
    useState<ProjectListResponse | null>(() =>
      getCachedProjectList(page, size, keyword),
    );
  const [isLoading, setIsLoading] = useState(
    () => getCachedProjectList(page, size, keyword) === null,
  );
  const [error, setError] = useState<string | null>(null);

  const normalizedKeyword = keyword.trim();
  const cachedProjectList = getCachedProjectList(
    page,
    size,
    normalizedKeyword,
  );
  const currentProjectList = cachedProjectList ?? projectList;

  useEffect(
    () =>
      subscribeProjectList(() => {
        const updatedProjectList = getCachedProjectList(
          page,
          size,
          normalizedKeyword,
        );

        if (updatedProjectList) {
          setProjectList(updatedProjectList);
        }
      }),
    [page, size, normalizedKeyword],
  );

  useEffect(() => {
    let isActive = true;

    const fetchProjectList = async () => {
      const cachedResponse = getCachedProjectList(
        page,
        size,
        normalizedKeyword,
      );

      setIsLoading(cachedResponse === null);
      setError(null);

      if (cachedResponse === null) {
        setProjectList(null);
      }

      try {
        const response = await getProjectList(
          page,
          size,
          normalizedKeyword,
        );

        if (isActive) {
          setProjectList(response);
        }

        const nextPage = response.page + 1;

        if (!normalizedKeyword && nextPage < response.totalPages) {
          void prefetchProjectList(nextPage, size).catch(
            () => undefined,
          );
        }
      } catch (caughtError) {
        if (isActive) {
          setError(
            apiErrorMessage(caughtError, "프로젝트 목록 조회에 실패했습니다."),
          );
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
  }, [page, size, normalizedKeyword]);

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
