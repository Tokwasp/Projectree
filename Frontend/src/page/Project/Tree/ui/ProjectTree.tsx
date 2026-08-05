import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import style from "../css/ProjectTree.module.css";
import { NODE_VISUALS, SpaceTree } from "../components/SpaceTree";
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
 *
 * 단, 선택된 결정 아래는 타입이 꺼져 있어도 되살린다(`keepAll`) — 결정을 눌렀는데
 * 하위가 안 보이면 선택의 의미가 없다. 이때만 범례 체크와 화면이 의도적으로 어긋난다.
 */
const pruneByType = (
  node: TreeNodeInput,
  visibility: NodeTypeVisibility,
  selectedDecisionId: string | null,
  keepAll = false,
): TreeNodeInput | null => {
  if (!keepAll && node.type !== "root" && !visibility[node.type]) return null;

  const keepChildren = keepAll || node.id === selectedDecisionId;
  const children = node.children
    ?.map((child) =>
      pruneByType(child, visibility, selectedDecisionId, keepChildren),
    )
    .filter((child): child is TreeNodeInput => child !== null);

  return { ...node, children };
};

/** 패널 폭. 3D 오버레이 버튼을 이만큼 왼쪽으로 밀어야 패널에 가리지 않는다. */
const DETAIL_PANEL_WIDTH = 340;

interface DecisionSelection {
  decision: TreeNodeInput;
  categoryTitle?: string;
  tasks: { node: TreeNodeInput; issues: TreeNodeInput[] }[];
  issueCount: number;
  /** 강조할 노드 — 조상(루트·카테고리) 경로와 결정 아래 전체. */
  highlightIds: Set<string>;
}

const collectIds = (node: TreeNodeInput, into: Set<string>) => {
  into.add(node.id);
  node.children?.forEach((child) => collectIds(child, into));
};

/**
 * 선택된 결정 노드와, 모달·강조에 필요한 주변 정보를 한 번의 순회로 모은다.
 * 하위 작업·이슈는 이미 트리 응답 안에 다 들어 있어 추가 요청이 필요하지 않다.
 */
const findDecisionSelection = (
  root: TreeNodeInput,
  decisionId: string,
): DecisionSelection | null => {
  const walk = (
    node: TreeNodeInput,
    ancestors: TreeNodeInput[],
  ): DecisionSelection | null => {
    if (node.id === decisionId) {
      const highlightIds = new Set(ancestors.map((ancestor) => ancestor.id));
      collectIds(node, highlightIds);

      const tasks = (node.children ?? []).map((task) => ({
        node: task,
        issues: task.children ?? [],
      }));

      return {
        decision: node,
        categoryTitle: ancestors.find(
          (ancestor) => ancestor.type === "category",
        )?.title,
        tasks,
        issueCount: tasks.reduce((sum, task) => sum + task.issues.length, 0),
        highlightIds,
      };
    }

    for (const child of node.children ?? []) {
      const found = walk(child, [...ancestors, node]);
      if (found) return found;
    }
    return null;
  };

  return walk(root, []);
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
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(
    null,
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

    return pruneByType(scoped, typeVisibility, selectedDecisionId);
  }, [
    tree,
    categories,
    selectedCategoryId,
    typeVisibility,
    selectedDecisionId,
  ]);

  // 필터로 선택된 결정이 트리에서 빠지면 selection도 같이 사라져 강조가 남지 않는다
  const selection = useMemo(
    () =>
      visibleTree && selectedDecisionId
        ? findDecisionSelection(visibleTree, selectedDecisionId)
        : null,
    [visibleTree, selectedDecisionId],
  );

  return (
    <div className={style.container}>
      {loading || !visibleTree ? (
        <p className={style.status}>트리를 불러오는 중입니다…</p>
      ) : (
        <>
          <SpaceTree
            data={visibleTree}
            highlightIds={selection?.highlightIds ?? null}
            onSelectDecision={setSelectedDecisionId}
            rightInset={selection ? DETAIL_PANEL_WIDTH : 0}
          />
          <CategoryFilter
            categories={categories}
            selectedId={selectedCategoryId}
            onSelect={setSelectedCategoryId}
          />
          <NodeTypeLegend
            visibility={typeVisibility}
            onChange={setTypeVisibility}
          />

          {selection && (
            <aside
              className={style.detailPanel}
              style={{ width: DETAIL_PANEL_WIDTH }}
            >
              <div className={style.detailHead}>
                <div>
                  {selection.categoryTitle && (
                    <span className={style.detailCategory}>
                      {selection.categoryTitle}
                    </span>
                  )}
                  <h2 className={style.detailTitle}>
                    {selection.decision.title}
                  </h2>
                </div>
                <button
                  type="button"
                  className={style.detailClose}
                  onClick={() => setSelectedDecisionId(null)}
                  aria-label="닫기"
                >
                  ×
                </button>
              </div>

              <p className={style.detailCount}>
                작업 {selection.tasks.length} · 이슈 {selection.issueCount}
              </p>

              {selection.tasks.length === 0 ? (
                <p className={style.detailEmpty}>연결된 작업이 없습니다.</p>
              ) : (
                <ul className={style.taskList}>
                  {selection.tasks.map(({ node, issues }) => (
                    <li key={node.id}>
                      <span className={style.taskTitle}>
                        <span
                          className={style.dot}
                          style={{ background: NODE_VISUALS.task.glowColor }}
                        />
                        {node.title}
                      </span>

                      {issues.length > 0 && (
                        <ul className={style.issueList}>
                          {issues.map((issue) => (
                            <li key={issue.id} className={style.issueItem}>
                              <span
                                className={style.dot}
                                style={{
                                  background: NODE_VISUALS.issue.glowColor,
                                }}
                              />
                              {issue.title}
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </aside>
          )}
        </>
      )}

      {usingMock && <span className={style.mockBadge}>샘플 데이터</span>}
    </div>
  );
}
