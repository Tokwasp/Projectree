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

/**
 * 노드별 nodeVersion을 id로 찾을 수 있게 모은다 — 화면에 그리는 TreeNodeInput은
 * 버전을 들고 있지 않아서, 수정 요청에 실을 값을 여기서 따로 챙겨 둔다.
 */
export const collectNodeVersions = (
  node: ProjectTreeNodeResponse,
  versions = new Map<string, number>(),
): Map<string, number> => {
  versions.set(node.id, node.nodeVersion ?? 0);
  node.children?.forEach((child) => collectNodeVersions(child, versions));
  return versions;
};

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
  expectedNodeVersion: number;
}

export const updateProjectNodeTitles = (
  projectId: number,
  nodes: ProjectNodeTitleUpdate[],
): Promise<void> =>
  apiRequest<void>(`/projects/${projectId}/nodes`, {
    method: "PATCH",
    body: JSON.stringify({ nodes }),
  });
