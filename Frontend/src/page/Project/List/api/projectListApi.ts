import { apiRequest } from "../../../../api/apiClient";

export interface ProjectListItemResponse {
  projectId: number;
  title: string;
  photoUrl: string | null;
  memberCnt: number;
}

export interface ProjectListResponse {
  projects: ProjectListItemResponse[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}

const projectListCache = new Map<string, ProjectListResponse>();
const pendingRequests = new Map<
  string,
  Promise<ProjectListResponse>
>();

let cacheVersion = 0;

const createCacheKey = (page: number, size: number) =>
  `${page}:${size}`;

export const getCachedProjectList = (
  page: number,
  size: number,
): ProjectListResponse | null =>
  projectListCache.get(createCacheKey(page, size)) ?? null;

export const getProjectList = (
  page: number,
  size: number,
): Promise<ProjectListResponse> => {
  const cacheKey = createCacheKey(page, size);
  const cachedProjectList = projectListCache.get(cacheKey);

  if (cachedProjectList) {
    return Promise.resolve(cachedProjectList);
  }

  const pendingRequest = pendingRequests.get(cacheKey);

  if (pendingRequest) {
    return pendingRequest;
  }

  const requestVersion = cacheVersion;

  const request = apiRequest<ProjectListResponse>(
    `/projects?page=${page}&size=${size}`,
  )
    .then((response) => {
      if (requestVersion === cacheVersion) {
        projectListCache.set(cacheKey, response);
      }

      return response;
    })
    .finally(() => {
      if (pendingRequests.get(cacheKey) === request) {
        pendingRequests.delete(cacheKey);
      }
    });

  pendingRequests.set(cacheKey, request);
  return request;
};

export const prefetchProjectList = (
  page: number,
  size: number,
): Promise<void> =>
  getProjectList(page, size).then(() => undefined);

export const addProjectToListCache = (
  project: ProjectListItemResponse,
) => {
  const cachedFirstPages = [...projectListCache.entries()].filter(
    ([, response]) => response.page === 0,
  );

  cacheVersion += 1;
  projectListCache.clear();
  pendingRequests.clear();

  cachedFirstPages.forEach(([cacheKey, response]) => {
    const totalElements = response.totalElements + 1;

    projectListCache.set(cacheKey, {
      ...response,
      projects: [project, ...response.projects].slice(
        0,
        response.size,
      ),
      totalElements,
      totalPages: Math.ceil(totalElements / response.size),
    });
  });
};

export const clearProjectListCache = () => {
  cacheVersion += 1;
  projectListCache.clear();
  pendingRequests.clear();
};
