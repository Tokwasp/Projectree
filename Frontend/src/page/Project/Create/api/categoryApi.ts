import { apiRequest } from "../../../../api/apiClient";

export interface NodeCategory {
  id: number;
  category: string;
}

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

  categoriesRequest = apiRequest<NodeCategory[]>("/categories")
    .then((categories) => {
      cachedCategories = categories;
      return categories;
    })
    .finally(() => {
      categoriesRequest = null;
    });

  return categoriesRequest;
};