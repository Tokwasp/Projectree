import style from "./ProjectCreateAside.module.css";

interface ProjectCreateAsideProps {
  projectTitle: string;
  nodeNames: string[];
  isLoading: boolean;
}

export default function ProjectCreateAside({
  projectTitle,
  nodeNames,
  isLoading,
}: ProjectCreateAsideProps) {
  const nodeRows = Array.from(
    { length: Math.ceil(nodeNames.length / 3) },
    (_, rowIndex) => nodeNames.slice(rowIndex * 3, rowIndex * 3 + 3),
  );

  return (
    <div className={style.asideColumn}>
      <aside className={style.tipCard} aria-labelledby="root-node-tip-title">
        <span className={style.tipLabel}>TIP</span>
        <h2 className={style.tipTitle} id="root-node-tip-title">
          프로젝트 구조
        </h2>
        <p className={style.tipDescription}>
          주요 분야가 기본 노드로 생성되어 아이디어와 회의 기록을 분류해요.
        </p>
      </aside>

      <section
        className={style.treePreview}
        aria-labelledby="tree-preview-title"
      >
        <h2 className={style.previewTitle} id="tree-preview-title">
          구조 미리보기
        </h2>

        <div className={style.projectNode}>
          {projectTitle.trim() || "프로젝트명"}
        </div>

        {nodeNames.length > 0 ? (
          <div className={style.rootNodeTree}>
            {nodeRows.map((row) => (
              <ul
                className={style.rootNodeRow}
                data-count={row.length}
                key={row.join("-")}
              >
                {row.map((rootNodeName) => (
                  <li className={style.rootNode} key={rootNodeName}>
                    {rootNodeName}
                  </li>
                ))}
              </ul>
            ))}
          </div>
        ) : (
          <p className={style.previewEmpty}>
            {isLoading ? "구조를 불러오는 중입니다." : "표시할 구조가 없습니다."}
          </p>
        )}
      </section>
    </div>
  );
}
