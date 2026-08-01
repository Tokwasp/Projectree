import { apiRequest } from "../../../../api/apiClient";
import type { NodeType, TreeNodeInput } from "../components/SpaceTree";

/**
 * 서버 응답 형태. 백엔드 노드 API가 아직 없어서 경로와 필드명은 가정이며,
 * 확정되면 이 파일과 toTreeNodeInput만 고치면 된다.
 */
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

/** 서버가 모르는 타입을 보내와도 화면이 깨지지 않게 task로 떨어뜨린다. */
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
