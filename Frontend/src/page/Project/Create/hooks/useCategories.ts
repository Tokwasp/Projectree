import { useEffect, useState } from "react";
import {
  getCachedCategories,
  getCategories,
  type NodeCategory,
} from "../api/categoryApi";

export default function useCategories() {
  const cachedCategories = getCachedCategories();

  const [categories, setCategories] = useState<NodeCategory[]>(
    cachedCategories ?? [],
  );
  const [isLoading, setIsLoading] = useState(!cachedCategories);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    const fetchCategories = async () => {
      try {
        const categoryData = await getCategories();

        if (isActive) {
          setCategories(categoryData);
        }
      } catch (caughtError) {
        const message =
          caughtError instanceof Error
            ? caughtError.message
            : "카테고리 조회에 실패했습니다.";

        if (isActive) {
          setError(message);
        }
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    };

    fetchCategories();

    return () => {
      isActive = false;
    };
  }, []);

  return {
    categories,
    isLoading,
    error,
  };
}