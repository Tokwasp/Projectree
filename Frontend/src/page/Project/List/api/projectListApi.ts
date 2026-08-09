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
const projectListListeners = new Set<() => void>();

let cacheVersion = 0;

const createCacheKey = (page: number, size: number) =>
  `${page}:${size}`;

const notifyProjectListListeners = () => {
  projectListListeners.forEach((listener) => listener());
};

export const subscribeProjectList = (listener: () => void) => {
  projectListListeners.add(listener);

  return () => {
    projectListListeners.delete(listener);
  };
};

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

  notifyProjectListListeners();
};

export const updateProjectInListCache = (
  projectId: number,
  updates: Partial<Pick<ProjectListItemResponse, "title" | "photoUrl">>,
) => {
  let isUpdated = false;

  projectListCache.forEach((response, cacheKey) => {
    const projects = response.projects.map((project) => {
      if (project.projectId !== projectId) {
        return project;
      }

      isUpdated = true;
      return { ...project, ...updates };
    });

    projectListCache.set(cacheKey, { ...response, projects });
  });

  if (isUpdated) {
    cacheVersion += 1;
    pendingRequests.clear();
    notifyProjectListListeners();
  }
};

export const clearProjectListCache = () => {
  cacheVersion += 1;
  projectListCache.clear();
  pendingRequests.clear();
};
