import type { NodeType } from "../SpaceTree";

export type FilterableNodeType = Exclude<NodeType, "root">;

export type NodeTypeVisibility = Record<FilterableNodeType, boolean>;

export const ALL_NODE_TYPES_VISIBLE: NodeTypeVisibility = {
  category: true,
  decision: true,
  task: true,
  issue: true,
};

export const NODE_TYPE_LABELS: Record<NodeType, string> = {
  root: "프로젝트",
  category: "카테고리",
  decision: "결정",
  task: "작업",
  issue: "이슈",
};

export const FILTERABLE_NODE_TYPES: FilterableNodeType[] = [
  "category",
  "decision",
  "task",
  "issue",
];
