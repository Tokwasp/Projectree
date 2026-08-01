import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import style from "../css/ProjectTree.module.css";
import { SpaceTree } from "../components/SpaceTree";
import CategoryFilter from "../components/CategoryFilter/CategoryFilter";
import { useProjectTree } from "../hooks/useProjectTree";

export default function ProjectTree() {
  const { projectId } = useParams<{ projectId: string }>();
  const { tree, loading, usingMock } = useProjectTree(Number(projectId));
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(
    null,
  );

  const categories = useMemo(
    () => tree?.children?.filter((node) => node.type === "category") ?? [],
    [tree],
  );

  /**
   * SpaceTree는 data 참조가 바뀔 때만 레이아웃을 다시 계산한다 —
   * 선택이 그대로면 같은 객체를 넘겨 물리 상태가 초기화되지 않게 한다.
   */
  const visibleTree = useMemo(() => {
    if (!tree) return null;
    if (!selectedCategoryId) return tree;

    const selected = categories.find(
      (category) => category.id === selectedCategoryId,
    );
    if (!selected) return tree;

    return { ...tree, children: [selected] };
  }, [tree, categories, selectedCategoryId]);

  return (
    <div className={style.container}>
      {loading || !visibleTree ? (
        <p className={style.status}>트리를 불러오는 중입니다…</p>
      ) : (
        <>
          <SpaceTree data={visibleTree} />
          <CategoryFilter
            categories={categories}
            selectedId={selectedCategoryId}
            onSelect={setSelectedCategoryId}
          />
        </>
      )}

      {usingMock && <span className={style.mockBadge}>샘플 데이터</span>}
    </div>
  );
}
