import style from "./ProjectCreateAside.module.css";

interface ProjectCreateAsideProps {
  projectTitle: string;
  rootNodeNames: string[];
}

export default function ProjectCreateAside({
  projectTitle,
  rootNodeNames,
}: ProjectCreateAsideProps) {
  const rootNodeRows = Array.from(
    { length: Math.ceil(rootNodeNames.length / 3) },
    (_, rowIndex) => rootNodeNames.slice(rowIndex * 3, rowIndex * 3 + 3),
  );

  return (
    <div className={style.asideColumn}>
      <aside className={style.tipCard} aria-labelledby="root-node-tip-title">
        <span className={style.tipLabel}>TIP</span>
        <h2 className={style.tipTitle} id="root-node-tip-title">
          루트 노드란?
        </h2>
        <p className={style.tipDescription}>
          프로젝트의 주요 분야를 선택하면 아이디어와 회의 기록을 분류하는
          시작점이 돼요.
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

        {rootNodeNames.length > 0 ? (
          <div className={style.rootNodeTree}>
            {rootNodeRows.map((row) => (
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
          <p className={style.previewEmpty}>루트 노드를 선택해주세요.</p>
        )}
      </section>
    </div>
  );
}
