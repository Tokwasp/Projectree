import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import style from "../css/ProjectTree.module.css";
import { NODE_VISUALS, SpaceTree } from "../components/SpaceTree";
import type { PickMode, TreeNodeInput } from "../components/SpaceTree";
import CategoryFilter from "../components/CategoryFilter/CategoryFilter";
import NodeTypeLegend from "../components/NodeTypeLegend/NodeTypeLegend";
import {
  ALL_NODE_TYPES_VISIBLE,
  type NodeTypeVisibility,
} from "../components/NodeTypeLegend/nodeTypeVisibility";
import { useProjectTree } from "../hooks/useProjectTree";
import {
  deleteProjectNodes,
  updateProjectNodeTitles,
} from "../api/projectTreeApi";
import { apiErrorMessage } from "../../../../api/apiClient";
import { toast } from "../../../../store/toastStore";

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

const DETAIL_PANEL_WIDTH = 340;

interface DecisionSelection {
  decision: TreeNodeInput;
  categoryTitle?: string;
  children: { node: TreeNodeInput; issues: TreeNodeInput[] }[];
  taskCount: number;
  issueCount: number;
  highlightIds: Set<string>;
}

const collectIds = (node: TreeNodeInput, into: Set<string>) => {
  into.add(node.id);
  node.children?.forEach((child) => collectIds(child, into));
};

const findNodeWithAncestors = (
  root: TreeNodeInput,
  nodeId: string,
  ancestors: TreeNodeInput[] = [],
): { node: TreeNodeInput; ancestors: TreeNodeInput[] } | null => {
  if (root.id === nodeId) return { node: root, ancestors };

  for (const child of root.children ?? []) {
    const found = findNodeWithAncestors(child, nodeId, [...ancestors, root]);
    if (found) return found;
  }
  return null;
};

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

      const children = (node.children ?? []).map((child) => ({
        node: child,
        issues: child.children ?? [],
      }));

      return {
        decision: node,
        categoryTitle: ancestors.find(
          (ancestor) => ancestor.type === "category",
        )?.title,
        children,
        taskCount: children.filter(({ node: child }) => child.type === "task")
          .length,
        issueCount: children.reduce(
          (sum, { node: child, issues }) =>
            sum + (child.type === "issue" ? 1 : 0) + issues.length,
          0,
        ),
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
  const { tree, graphVersion, loading, usingMock, reload } = useProjectTree(
    Number(projectId),
  );
  const [selectedCategoryId, setSelectedCategoryId] = useState<string | null>(
    null,
  );
  const [typeVisibility, setTypeVisibility] = useState<NodeTypeVisibility>(
    ALL_NODE_TYPES_VISIBLE,
  );
  const [selectedDecisionId, setSelectedDecisionId] = useState<string | null>(
    null,
  );
  const [pickMode, setPickMode] = useState<PickMode | null>(null);
  const [checkedIds, setCheckedIds] = useState<Set<string>>(new Set());
  // 수정 모드에서 입력 중인 라벨. 노드를 고를 때 원래 제목으로 채워 둔다
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nodeById = useMemo(() => {
    const map = new Map<string, TreeNodeInput>();
    if (!tree) return map;

    const walk = (node: TreeNodeInput) => {
      map.set(node.id, node);
      node.children?.forEach(walk);
    };
    walk(tree);
    return map;
  }, [tree]);

  // Set은 넣은 순서를 지킨다 — 고른 순서대로 입력칸이 쌓인다
  const editTargets: TreeNodeInput[] = [];
  if (pickMode === "edit") {
    checkedIds.forEach((id) => {
      const node = nodeById.get(id);
      if (node) editTargets.push(node);
    });
  }

  const exitPickMode = () => {
    setPickMode(null);
    setCheckedIds(new Set());
    setDrafts({});
  };

  // 고르기 모드에서는 노드 클릭이 "고르기"라 상세 패널이 열리면 안 된다
  const enterPickMode = (mode: PickMode) => {
    setSelectedDecisionId(null);
    setCheckedIds(new Set());
    setDrafts({});
    setPickMode(mode);
  };

  const selectDecision = (decisionId: string | null) => {
    setSelectedDecisionId(decisionId);
  };

  const handleDelete = async () => {
    if (isSubmitting || checkedIds.size === 0) return;

    setIsSubmitting(true);

    try {
      await deleteProjectNodes(
        Number(projectId),
        [...checkedIds],
        graphVersion,
      );
      toast.success(`${checkedIds.size}개 노드를 삭제했습니다.`);
      exitPickMode();
      // 지운 노드가 화면에 남지 않도록 서버 트리를 다시 받는다
      reload();
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "노드를 삭제하지 못했습니다."));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleUpdate = async () => {
    if (isSubmitting || editTargets.length === 0) return;

    const updates = editTargets.map((node) => ({
      nodeId: node.id,
      title: (drafts[node.id] ?? node.title).trim(),
    }));

    // 빈 라벨은 화면에서 노드를 이름 없는 점으로 만든다 — 보내기 전에 막는다
    if (updates.some((update) => !update.title)) {
      toast.error("라벨을 비워 둘 수 없습니다.");
      return;
    }

    setIsSubmitting(true);

    try {
      await updateProjectNodeTitles(Number(projectId), updates);
      toast.success(`${updates.length}개 노드를 수정했습니다.`);
      exitPickMode();
      // 고친 라벨이 트리에 반영되도록 서버 트리를 다시 받는다
      reload();
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "노드를 수정하지 못했습니다."));
    } finally {
      setIsSubmitting(false);
    }
  };

  /**
   * 고른 노드는 자식까지 함께 죽는다 — 부모를 지우면 자식은 어차피 갈 곳이 없다.
   * 반대로 자식을 풀면 조상도 같이 푼다. "부모는 삭제, 자식은 유지"를 서버로
   * 보내면 앞뒤가 맞지 않기 때문이다.
   */
  const toggleDeleteTarget = (nodeId: string) => {
    if (!tree) return;

    const found = findNodeWithAncestors(tree, nodeId);
    if (!found) return;

    setCheckedIds((current) => {
      const next = new Set(current);
      const subtreeIds = new Set<string>();
      collectIds(found.node, subtreeIds);

      if (next.has(nodeId)) {
        subtreeIds.forEach((id) => next.delete(id));
        found.ancestors.forEach((ancestor) => next.delete(ancestor.id));
      } else {
        subtreeIds.forEach((id) => next.add(id));
      }

      return next;
    });
  };

  /** 라벨은 노드마다 따로 고치는 값이라, 삭제와 달리 자식·조상으로 번지지 않는다. */
  const toggleEditTarget = (nodeId: string) => {
    const node = nodeById.get(nodeId);
    if (!node) return;

    const picked = checkedIds.has(nodeId);

    setCheckedIds((current) => {
      const next = new Set(current);
      if (picked) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });

    setDrafts((current) => {
      if (!picked) return { ...current, [nodeId]: node.title };
      // 고르기를 풀면 적어 둔 라벨도 같이 버린다 — 다시 고르면 원래 제목에서 시작한다
      const next = { ...current };
      delete next[nodeId];
      return next;
    });
  };

  const togglePickTarget = (nodeId: string) => {
    if (pickMode === "edit") toggleEditTarget(nodeId);
    else toggleDeleteTarget(nodeId);
  };

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
            onSelectDecision={selectDecision}
            rightInset={selection ? DETAIL_PANEL_WIDTH : 0}
            pickMode={pickMode}
            pickedIds={checkedIds}
            onTogglePick={togglePickTarget}
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
                  onClick={() => selectDecision(null)}
                  aria-label="닫기"
                >
                  ×
                </button>
              </div>

              <p className={style.detailCount}>
                작업 {selection.taskCount} · 이슈 {selection.issueCount}
              </p>

              {selection.children.length === 0 ? (
                <p className={style.detailEmpty}>연결된 노드가 없습니다.</p>
              ) : (
                <ul className={style.taskList}>
                  {selection.children.map(({ node, issues }) => (
                    <li key={node.id}>
                      <span className={style.taskTitle}>
                        <span
                          className={style.dot}
                          style={{
                            background: NODE_VISUALS[node.type].glowColor,
                          }}
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
                                  background:
                                    NODE_VISUALS[issue.type].glowColor,
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

          {/* 고른 노드의 라벨 입력칸. 노드를 고르는 즉시 이 위에 쌓인다 */}
          {editTargets.length > 0 && (
            <div className={style.editPanel}>
              {editTargets.map((node) => (
                <div key={node.id} className={style.editRow}>
                  <span
                    className={style.dot}
                    style={{ background: NODE_VISUALS[node.type].glowColor }}
                  />
                  <input
                    className={style.editInput}
                    value={drafts[node.id] ?? node.title}
                    onChange={(event) =>
                      setDrafts((current) => ({
                        ...current,
                        [node.id]: event.target.value,
                      }))
                    }
                    disabled={isSubmitting}
                    aria-label={`${node.title} 라벨`}
                  />
                  <button
                    type="button"
                    className={style.editRemove}
                    onClick={() => toggleEditTarget(node.id)}
                    disabled={isSubmitting}
                    aria-label="목록에서 빼기"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* 하단 가운데 — 네 모서리는 필터·범례·보기전환·줌이 이미 쓰고 있다 */}
          <div className={style.actionBar}>
            {pickMode === null && (
              <>
                <button
                  type="button"
                  className={style.actionButton}
                  onClick={() => enterPickMode("edit")}
                >
                  노드 수정
                </button>
                <button
                  type="button"
                  className={style.actionButton}
                  onClick={() => enterPickMode("delete")}
                >
                  노드 삭제
                </button>
              </>
            )}

            {pickMode === "edit" && (
              <>
                <span className={style.actionHint}>
                  {checkedIds.size === 0
                    ? "수정할 노드를 선택하세요. 고른 노드의 라벨을 고칠 수 있습니다."
                    : `${checkedIds.size}개 노드의 라벨을 수정합니다.`}
                </span>
                <button
                  type="button"
                  className={style.editConfirm}
                  onClick={handleUpdate}
                  disabled={checkedIds.size === 0 || isSubmitting}
                >
                  {isSubmitting ? "수정 중…" : "수정"}
                </button>
                <button
                  type="button"
                  className={style.actionButton}
                  onClick={exitPickMode}
                  disabled={isSubmitting}
                >
                  취소
                </button>
              </>
            )}

            {pickMode === "delete" && (
              <>
                <span className={style.actionHint}>
                  {checkedIds.size === 0
                    ? "삭제할 노드를 선택하세요. 자식 노드도 함께 삭제됩니다."
                    : `${checkedIds.size}개 노드를 삭제합니다.`}
                </span>
                <button
                  type="button"
                  className={style.deleteConfirm}
                  onClick={handleDelete}
                  disabled={checkedIds.size === 0 || isSubmitting}
                >
                  {isSubmitting ? "삭제 중…" : "삭제"}
                </button>
                <button
                  type="button"
                  className={style.actionButton}
                  onClick={exitPickMode}
                  disabled={isSubmitting}
                >
                  취소
                </button>
              </>
            )}
          </div>
        </>
      )}

      {usingMock && <span className={style.mockBadge}>샘플 데이터</span>}
    </div>
  );
}
