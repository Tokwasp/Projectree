import style from "./CategoryFilter.module.css";
import type { TreeNodeInput } from "../SpaceTree";

interface CategoryFilterProps {
  categories: TreeNodeInput[];
  /** null이면 전체 보기 */
  selectedId: string | null;
  onSelect: (categoryId: string | null) => void;
}

export default function CategoryFilter({
  categories,
  selectedId,
  onSelect,
}: CategoryFilterProps) {
  if (categories.length === 0) return null;

  return (
    <div className={style.container} role="group" aria-label="카테고리 필터">
      <button
        className={selectedId === null ? style.chipActive : style.chip}
        type="button"
        onClick={() => onSelect(null)}
        aria-pressed={selectedId === null}
      >
        전체
      </button>

      {categories.map((category) => (
        <button
          key={category.id}
          className={selectedId === category.id ? style.chipActive : style.chip}
          type="button"
          onClick={() => onSelect(category.id)}
          aria-pressed={selectedId === category.id}
        >
          {category.title}
        </button>
      ))}
    </div>
  );
}
