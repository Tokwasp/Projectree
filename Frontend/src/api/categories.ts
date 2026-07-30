export interface NodeCategory {
  id: number;
  name: string;
}

interface ApiResponse<T> {
  status: number;
  message: string;
  data: T;
}

interface ApiErrorResponse {
  status: number;
  errorCode: string;
  errorMessage: string;
}

const BASE_URL = import.meta.env.VITE_BASE_URL;

let cachedCategories: NodeCategory[] | null = null;
let categoriesRequest: Promise<NodeCategory[]> | null = null;

export const getCachedCategories = () => cachedCategories;

export const getCategories = (): Promise<NodeCategory[]> => {
  if (cachedCategories) {
    return Promise.resolve(cachedCategories);
  }

  if (categoriesRequest) {
    return categoriesRequest;
  }

  categoriesRequest = fetch(`${BASE_URL}/categories`, {
    credentials: "include",
  })
    .then(async (response) => {
      const responseData:
        | ApiResponse<NodeCategory[]>
        | ApiErrorResponse = await response.json();

      if (!response.ok) {
        throw new Error(
          "errorMessage" in responseData
            ? responseData.errorMessage
            : responseData.message || "카테고리 조회에 실패했습니다.",
        );
      }

      const categories = (responseData as ApiResponse<NodeCategory[]>).data;
      cachedCategories = categories;
      return categories;
    })
    .finally(() => {
      categoriesRequest = null;
    });

  return categoriesRequest;
};
