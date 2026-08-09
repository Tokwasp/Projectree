import { useCallback, useEffect, useState } from "react";
import {
  collectNodeVersions,
  getProjectTree,
  toTreeNodeInput,
} from "../api/projectTreeApi";
import type { TreeNodeInput } from "../components/SpaceTree";
import { mockProjectTree } from "../../../../mocks/TreeMocks";

export const useProjectTree = (projectId: number) => {
  const [tree, setTree] = useState<TreeNodeInput | null>(null);
  // 삭제 요청이 expectedGraphVersion으로 되돌려 보내야 하는 값
  const [graphVersion, setGraphVersion] = useState(0);
  // 수정 요청이 노드마다 expectedNodeVersion으로 되돌려 보내야 하는 값
  const [nodeVersions, setNodeVersions] = useState<Map<string, number>>(
    new Map(),
  );
  const [loading, setLoading] = useState(true);
  // 노드 API가 아직 없어서 실패하면 샘플로 떨어진다 — 화면에 그 사실을 표시하기 위한 값
  const [usingMock, setUsingMock] = useState(false);
  // 노드를 지운 뒤 서버 트리를 다시 받아오기 위한 값
  const [reloadToken, setReloadToken] = useState(0);

  const reload = useCallback(() => setReloadToken((token) => token + 1), []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await getProjectTree(projectId);
        if (cancelled) return;
        setTree(toTreeNodeInput(response.root));
        setGraphVersion(response.graphVersion);
        setNodeVersions(collectNodeVersions(response.root));
        setUsingMock(false);
      } catch {
        if (cancelled) return;
        setTree(mockProjectTree);
        setGraphVersion(0);
        setNodeVersions(new Map());
        setUsingMock(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [projectId, reloadToken]);

  return { tree, graphVersion, nodeVersions, loading, usingMock, reload };
};
