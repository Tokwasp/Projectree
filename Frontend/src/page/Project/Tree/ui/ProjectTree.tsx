import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import style from "../css/ProjectTree.module.css";
import { SpaceTree } from "../components/SpaceTree";
import type { TreeNodeInput } from "../components/SpaceTree";
import CategoryFilter from "../components/CategoryFilter/CategoryFilter";
import NodeTypeLegend from "../components/NodeTypeLegend/NodeTypeLegend";
import {
  ALL_NODE_TYPES_VISIBLE,
  type NodeTypeVisibility,
} from "../components/NodeTypeLegend/nodeTypeVisibility";
import { useProjectTree } from "../hooks/useProjectTree";

/**
 * 꺼진 타입의 노드를 트리에서 아예 들어낸다. 화면에서 감추는 게 아니라 데이터에서
 * 빼기 때문에 그만큼 DOM(라벨)과 물리 계산이 통째로 줄어든다.
 *
 * 계층이 root → category → decision → task → issue 라, 중간 단계를 끄면 그 아래는
 * 매달릴 부모가 없어진다. 체크 상태도 범례에서 함께 꺼지므로 화면과 어긋나지 않는다.
 */
const pruneByType = (
  node: TreeNodeInput,
  visibility: NodeTypeVisibility,
): TreeNodeInput | null => {
  if (node.type !== "root" && !visibility[node.type]) return null;

  const children = node.children
    ?.map((child) => pruneByType(child, visibility))
    .filter((child): child is TreeNodeInput => child !== null);

  return { ...node, children };
};

export default function ProjectTree() {
  const { projectId } = useParams<{ projectId: string }>();
  const { tree, loading, usingMock } = useProjectTree(Number(projectId));
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(
    null,
  );
  const [typeVisibility, setTypeVisibility] = useState<NodeTypeVisibility>(
    ALL_NODE_TYPES_VISIBLE,
  );

  const categories = useMemo(
    () => tree?.children?.filter((node) => node.type === "category") ?? [],
    [tree],
  );

  const visibleTree = useMemo(() => {
    if (!tree) return null;

    const selected = selectedCategoryId
      ? categories.find((category) => category.id === selectedCategoryId)
      : undefined;
    const scoped = selected ? { ...tree, children: [selected] } : tree;

    return pruneByType(scoped, typeVisibility);
  }, [tree, categories, selectedCategoryId, typeVisibility]);

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
          <NodeTypeLegend
            visibility={typeVisibility}
            onChange={setTypeVisibility}
          />
        </>
      )}

      {usingMock && <span className={style.mockBadge}>샘플 데이터</span>}
    </div>
  );
}
