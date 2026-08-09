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

export const deleteProjectNodes = (
  projectId: number,
  nodeIds: string[],
  expectedGraphVersion: number,
): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}/nodes/delete`, {
    method: "POST",
    body: JSON.stringify({ nodeIds, expectedGraphVersion }),
  });

export interface ProjectNodeTitleUpdate {
  nodeId: string;
  title: string;
}

/** 여러 노드의 라벨을 한 번에 고친다 — 삭제와 같이 id 목록을 한 요청으로 보낸다. */
export const updateProjectNodeTitles = (
  projectId: number,
  nodes: ProjectNodeTitleUpdate[],
): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}/nodes`, {
    method: "PATCH",
    body: JSON.stringify({ nodes }),
  });
