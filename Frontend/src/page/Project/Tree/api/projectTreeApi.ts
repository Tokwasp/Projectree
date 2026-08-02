import { apiRequest } from "../../../../api/apiClient";
import type { NodeType, TreeNodeInput } from "../components/SpaceTree";

// 서버 응답
export interface ProjectTreeNodeResponse {
  nodeId: number | string;
  type: string;
  title: string;
  children?: ProjectTreeNodeResponse[];
}

const NODE_TYPES: NodeType[] = [
  "root",
  "category",
  "decision",
  "task",
  "issue",
];

const toNodeType = (raw: string): NodeType => {
  const normalized = raw?.toLowerCase() as NodeType;
  return NODE_TYPES.includes(normalized) ? normalized : "task";
};

/** id는 트리 전체에서 유일해야 한다 — 레이아웃 회전값과 물리 상태의 키로 쓰인다. */
export const toTreeNodeInput = (
  node: ProjectTreeNodeResponse,
): TreeNodeInput => ({
  id: String(node.nodeId),
  type: toNodeType(node.type),
  title: node.title,
  children: node.children?.map(toTreeNodeInput),
});

export const getProjectTree = (
  projectId: number,
): Promise<ProjectTreeNodeResponse> =>
  apiRequest<ProjectTreeNodeResponse>(`/projects/${projectId}/nodes`);
