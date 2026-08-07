import { useEffect, useState } from "react";
import { getProjectTree, toTreeNodeInput } from "../api/projectTreeApi";
import type { TreeNodeInput } from "../components/SpaceTree";
import { mockProjectTree } from "../../../../mocks/TreeMocks";

export const useProjectTree = (projectId: number) => {
  const [tree, setTree] = useState<TreeNodeInput | null>(null);
  const [loading, setLoading] = useState(true);
  // 노드 API가 아직 없어서 실패하면 샘플로 떨어진다 — 화면에 그 사실을 표시하기 위한 값
  const [usingMock, setUsingMock] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const response = await getProjectTree(projectId);
        if (cancelled) return;
        setTree(toTreeNodeInput(response.root));
        setUsingMock(false);
      } catch {
        if (cancelled) return;
        setTree(mockProjectTree);
        setUsingMock(true);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void load();

    return () => {
      cancelled = true;
    };
  }, [projectId]);

  return { tree, loading, usingMock };
};
