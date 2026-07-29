import style from "../../css/meeting/MeetingNodeReviewModal.module.css";
import type {
  NodeCandidate,
  NodeCandidateType,
  NodeCategoryResult,
} from "../../types/MeetingNode";

type NodeTextField = "title" | "content";

interface NodeCandidateItemProps {
  node: NodeCandidate;
  categoryId: number;
  categories: NodeCategoryResult[];
  isEditing: boolean;
  onTextChange: (
    categoryId: number,
    candidateId: string,
    field: NodeTextField,
    value: string,
  ) => void;
  onTypeChange: (
    categoryId: number,
    candidateId: string,
    type: NodeCandidateType,
  ) => void;
  onCategoryChange: (
    categoryId: number,
    candidateId: string,
    targetCategoryId: number,
  ) => void;
  onDelete: (
    categoryId: number,
    candidateId: string,
  ) => void;
}

const nodeTypes: NodeCandidateType[] = [
  "DECISION",
  "ACTION",
  "ISSUE",
];

const typeClassNames: Record<NodeCandidateType, string> = {
  DECISION: style.decision,
  ACTION: style.action,
  ISSUE: style.issue,
};

const typeLabels: Record<NodeCandidateType, string> = {
  DECISION: "✓ 결정",
  ACTION: "→ 액션",
  ISSUE: "△ 이슈",
};

function getNodeType(value: string): NodeCandidateType {
  if (value === "ACTION" || value === "ISSUE") {
    return value;
  }

  return "DECISION";
}

export default function NodeCandidateItem({
  node,
  categoryId,
  categories,
  isEditing,
  onTextChange,
  onTypeChange,
  onCategoryChange,
  onDelete,
}: NodeCandidateItemProps) {
  return (
    <article
      className={`${style.nodeCard} ${
        typeClassNames[node.type]
      } ${isEditing ? style.editingCard : ""}`}
    >
      {isEditing ? (
        <>
          <div className={style.selectRow}>
            <label>
              <span>카테고리</span>
              <select
                value={categoryId}
                onChange={(event) =>
                  onCategoryChange(
                    categoryId,
                    node.candidateId,
                    Number(event.target.value),
                  )
                }
              >
                {categories.map((category) => (
                  <option
                    value={category.categoryId}
                    key={category.categoryId}
                  >
                    {category.categoryName}
                  </option>
                ))}
              </select>
            </label>

            <label>
              <span>유형</span>
              <select
                value={node.type}
                onChange={(event) =>
                  onTypeChange(
                    categoryId,
                    node.candidateId,
                    getNodeType(event.target.value),
                  )
                }
              >
                {nodeTypes.map((nodeType) => (
                  <option value={nodeType} key={nodeType}>
                    {typeLabels[nodeType]}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <button
            className={style.deleteNodeButton}
            type="button"
            onClick={() =>
              onDelete(categoryId, node.candidateId)
            }
          >
            삭제
          </button>

          <label className={style.editField}>
            <span>제목</span>
            <input
              type="text"
              value={node.title}
              onChange={(event) =>
                onTextChange(
                  categoryId,
                  node.candidateId,
                  "title",
                  event.target.value,
                )
              }
            />
          </label>

          <label className={style.editField}>
            <span>내용</span>
            <textarea
              value={node.content}
              onChange={(event) =>
                onTextChange(
                  categoryId,
                  node.candidateId,
                  "content",
                  event.target.value,
                )
              }
            />
          </label>
        </>
      ) : (
        <>
          <div className={style.nodeTitleRow}>
            <span className={style.typeBadge}>
              {typeLabels[node.type]}
            </span>
            <h4>{node.title}</h4>
          </div>

          <p className={style.nodeContent}>{node.content}</p>
        </>
      )}
    </article>
  );
}
