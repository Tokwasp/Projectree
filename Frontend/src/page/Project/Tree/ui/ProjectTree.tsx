import { useParams } from "react-router-dom";
import style from "../css/ProjectTree.module.css";
import { SpaceTree } from "../components/SpaceTree";
import { useProjectTree } from "../hooks/useProjectTree";

export default function ProjectTree() {
  const { projectId } = useParams<{ projectId: string }>();
  const { tree, loading, usingMock } = useProjectTree(Number(projectId));

  return (
    <div className={style.container}>
      {loading || !tree ? (
        <p className={style.status}>트리를 불러오는 중입니다…</p>
      ) : (
        <SpaceTree data={tree} />
      )}

      {usingMock && <span className={style.mockBadge}>샘플 데이터</span>}
    </div>
  );
}
