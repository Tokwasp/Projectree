import { apiRequest } from "../../../../api/apiClient";
import type { NodeType, TreeNodeInput } from "../components/SpaceTree";

export type ProjectTreeNodeKind =
  | "PROJECT_ROOT"
  | "CATEGORY_ROOT"
  | "GRAPH_NODE";

export type ProjectTreeNodeType = "DECISION" | "ACTION" | "ISSUE";

// 서버 응답
export interface ProjectTreeNodeResponse {
  id: string;
  kind: ProjectTreeNodeKind;
  title: string;
  category?: string;
  nodeType?: ProjectTreeNodeType;
  sourceMeetingId?: number;
  nodeVersion?: number;
  updatedAt?: string;
  children?: ProjectTreeNodeResponse[];
}

export interface ProjectTreeResponse {
  projectId: number;
  graphVersion: number;
  graphSyncedAt: string;
  root: ProjectTreeNodeResponse;
}

const NODE_TYPE_BY_SERVER: Record<ProjectTreeNodeType, NodeType> = {
  DECISION: "decision",
  ACTION: "task",
  ISSUE: "issue",
};

const toNodeType = ({ kind, nodeType }: ProjectTreeNodeResponse): NodeType => {
  if (kind === "PROJECT_ROOT") return "root";
  if (kind === "CATEGORY_ROOT") return "category";
  return (nodeType && NODE_TYPE_BY_SERVER[nodeType]) ?? "task";
};

export const toTreeNodeInput = (
  node: ProjectTreeNodeResponse,
): TreeNodeInput => ({
  id: node.id,
  type: toNodeType(node),
  title: node.title,
  children: node.children?.map(toTreeNodeInput),
});

export const getProjectTree = (
  projectId: number,
): Promise<ProjectTreeResponse> =>
  apiRequest<ProjectTreeResponse>(`/projects/${projectId}/nodes/tree`);
