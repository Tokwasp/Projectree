import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import type { ProjectSummary } from "../../../../types/Project";
import {
  getProjectList,
  type ProjectListResponse,
} from "../api/projectListApi";

export default function useProjectList(page: number, size: number) {
  const [projectList, setProjectList] =
    useState<ProjectListResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const cacheRef = useRef(new Map<string, ProjectListResponse>());
  const pendingRequestsRef = useRef(
    new Map<string, Promise<ProjectListResponse>>(),
  );

  const requestProjectList = useCallback(
    (targetPage: number): Promise<ProjectListResponse> => {
      const cacheKey = `${targetPage}:${size}`;
      const cachedProjectList = cacheRef.current.get(cacheKey);

      if (cachedProjectList) {
        return Promise.resolve(cachedProjectList);
      }

      const pendingRequest = pendingRequestsRef.current.get(cacheKey);

      if (pendingRequest) {
        return pendingRequest;
      }

      const request = getProjectList(targetPage, size)
        .then((response) => {
          cacheRef.current.set(cacheKey, response);
          return response;
        })
        .finally(() => {
          pendingRequestsRef.current.delete(cacheKey);
        });

      pendingRequestsRef.current.set(cacheKey, request);
      return request;
    },
    [size],
  );

  useEffect(() => {
    let isActive = true;

    const fetchProjectList = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await requestProjectList(page);

        if (isActive) {
          setProjectList(response);
        }

        const nextPage = response.page + 1;

        if (nextPage < response.totalPages) {
          void requestProjectList(nextPage).catch(() => undefined);
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
  }, [page, requestProjectList]);

  const projects: ProjectSummary[] =
    projectList?.projects.map((project) => ({
      projectId: project.projectId,
      title: project.title,
      memberCount: project.memberCnt,
      thumbnailUrl: project.photoUrl ?? undefined,
    })) ?? [];

  return {
    projects,
    page: projectList?.page ?? page,
    totalElements: projectList?.totalElements ?? 0,
    totalPages: projectList?.totalPages ?? 0,
    isLoading,
    error,
  };
}
