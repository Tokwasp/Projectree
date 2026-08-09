import style from "../../css/MeetingNodeReviewModal.module.css";
import type { NodeCategoryResult } from "../../../../../types/MeetingNode";

interface NodeCategoryTabsProps {
  categories: NodeCategoryResult[];
  activeCategoryId?: number;
  onSelect: (categoryId: number) => void;
}

export default function NodeCategoryTabs({
  categories,
  activeCategoryId,
  onSelect,
}: NodeCategoryTabsProps) {
  return (
    <div
      className={style.categoryTabs}
      role="tablist"
      aria-label="노드 카테고리"
    >
      {categories.map((category) => {
        const isActive =
          category.categoryId === activeCategoryId;

        return (
          <button
            className={`${style.categoryTab} ${
              isActive ? style.activeTab : ""
            }`}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onSelect(category.categoryId)}
            key={category.categoryId}
          >
            <span>{category.categoryName}</span>
            <strong>{category.nodes.length}</strong>
          </button>
        );
      })}
    </div>
  );
}
