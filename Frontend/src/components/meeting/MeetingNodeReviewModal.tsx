import {
  useCallback,
  useEffect,
  useState,
  type FormEvent,
} from "react";
import style from "../../css/meeting/MeetingNodeReviewModal.module.css";
import type {
  MeetingNodeResult,
  NodeCandidate,
  NodeCandidateType,
} from "../../types/MeetingNode";
import NodeCandidateItem from "./NodeCandidateItem";
import NodeCategoryTabs from "./NodeCategoryTabs";

interface MeetingNodeReviewModalProps {
  isOpen: boolean;
  result: MeetingNodeResult;
  onClose: () => void;
  onSave: (result: MeetingNodeResult) => void;
}

type NodeTextField = "title" | "content";

const nodeTypeOrder: Record<NodeCandidateType, number> = {
  DECISION: 0,
  ACTION: 1,
  ISSUE: 2,
};

function sortNodesByType(nodes: NodeCandidate[]) {
  return [...nodes].sort(
    (firstNode, secondNode) =>
      nodeTypeOrder[firstNode.type] -
      nodeTypeOrder[secondNode.type],
  );
}

export default function MeetingNodeReviewModal({
  isOpen,
  result,
  onClose,
  onSave,
}: MeetingNodeReviewModalProps) {
  if (!isOpen) {
    return null;
  }

  return (
    <MeetingNodeReviewDialog
      result={result}
      onClose={onClose}
      onSave={onSave}
    />
  );
}

type MeetingNodeReviewDialogProps = Omit<
  MeetingNodeReviewModalProps,
  "isOpen"
>;

function MeetingNodeReviewDialog({
  result,
  onClose,
  onSave,
}: MeetingNodeReviewDialogProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [categories, setCategories] = useState(result.categories);
  const [activeCategoryId, setActiveCategoryId] = useState(
    result.categories[0]?.categoryId,
  );

  const activeCategory =
    categories.find(
      (category) => category.categoryId === activeCategoryId,
    ) ?? categories[0];

  const isDirty =
    JSON.stringify(categories) !==
    JSON.stringify(result.categories);

  const handleClose = useCallback(() => {
    if (
      isEditing &&
      isDirty &&
      !window.confirm(
        "수정한 내용이 저장되지 않았습니다. 닫으시겠습니까?",
      )
    ) {
      return;
    }

    setCategories(result.categories);
    setIsEditing(false);
    setActiveCategoryId(result.categories[0]?.categoryId);
    onClose();
  }, [isDirty, isEditing, onClose, result.categories]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        handleClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [handleClose]);

  const handleTextChange = (
    categoryId: number,
    candidateId: string,
    field: NodeTextField,
    value: string,
  ) => {
    setCategories((currentCategories) =>
      currentCategories.map((category) =>
        category.categoryId === categoryId
          ? {
              ...category,
              nodes: category.nodes.map((node) =>
                node.candidateId === candidateId
                  ? { ...node, [field]: value }
                  : node,
              ),
            }
          : category,
      ),
    );
  };

  const handleTypeChange = (
    categoryId: number,
    candidateId: string,
    nextType: NodeCandidateType,
  ) => {
    setCategories((currentCategories) =>
      currentCategories.map((category) =>
        category.categoryId === categoryId
          ? {
              ...category,
              nodes: sortNodesByType(
                category.nodes.map((node) =>
                  node.candidateId === candidateId
                    ? { ...node, type: nextType }
                    : node,
                ),
              ),
            }
          : category,
      ),
    );
  };

  const handleCategoryChange = (
    sourceCategoryId: number,
    candidateId: string,
    targetCategoryId: number,
  ) => {
    if (sourceCategoryId === targetCategoryId) {
      return;
    }

    setCategories((currentCategories) => {
      const sourceCategory = currentCategories.find(
        (category) => category.categoryId === sourceCategoryId,
      );
      const targetNode = sourceCategory?.nodes.find(
        (node) => node.candidateId === candidateId,
      );

      if (!targetNode) {
        return currentCategories;
      }

      return currentCategories.map((category) => {
        if (category.categoryId === sourceCategoryId) {
          return {
            ...category,
            nodes: category.nodes.filter(
              (node) => node.candidateId !== candidateId,
            ),
          };
        }

        if (category.categoryId === targetCategoryId) {
          return {
            ...category,
            nodes: sortNodesByType([
              ...category.nodes,
              targetNode,
            ]),
          };
        }

        return category;
      });
    });
  };

  const handleDeleteNode = (
    categoryId: number,
    candidateId: string,
  ) => {
    setCategories((currentCategories) =>
      currentCategories.map((category) =>
        category.categoryId === categoryId
          ? {
              ...category,
              nodes: category.nodes.filter(
                (node) => node.candidateId !== candidateId,
              ),
            }
          : category,
      ),
    );
  };

  const hasInvalidNode = categories.some((category) =>
    category.nodes.some(
      (node) =>
        node.title.trim().length === 0 ||
        node.content.trim().length === 0,
    ),
  );

  const hasNode = categories.some(
    (category) => category.nodes.length > 0,
  );

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!hasNode || hasInvalidNode) {
      return;
    }

    const normalizedCategories = categories.map((category) => ({
      ...category,
      nodes: sortNodesByType(
        category.nodes.map((node) => ({
          ...node,
          title: node.title.trim(),
          content: node.content.trim(),
        })),
      ),
    }));

    onSave({
      ...result,
      categories: normalizedCategories,
    });

    setIsEditing(false);
  };

  return (
    <div
      className={style.overlay}
      role="presentation"
      onClick={handleClose}
    >
      <section
        className={style.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="meeting-node-review-title"
        onClick={(event) => event.stopPropagation()}
      >
        <form className={style.form} onSubmit={handleSubmit}>
          <header className={style.header}>
            <div>
              <div className={style.titleRow}>
                <h2
                  className={style.title}
                  id="meeting-node-review-title"
                >
                  AI 노드 분류 검토
                </h2>

                <span className={style.status}>분석 완료</span>
              </div>

              <p className={style.description}>
                AI가 추출한 노드 분류를 검토하고 수정해 주세요.
              </p>
            </div>

            {!isEditing && (
              <button
                className={style.editButton}
                type="button"
                onClick={() => setIsEditing(true)}
              >
                수정
              </button>
            )}
          </header>

          <div className={style.content}>
            <div className={style.meetingInfo}>
              <strong>{result.meetingTitle}</strong>
              <span>
                {result.categories.length}개 카테고리에서{" "}
                {result.categories.reduce(
                  (total, category) =>
                    total + category.nodes.length,
                  0,
                )}
                개의 노드 후보를 추출했습니다.
              </span>
            </div>

            <NodeCategoryTabs
              categories={categories}
              activeCategoryId={activeCategory?.categoryId}
              onSelect={setActiveCategoryId}
            />

            {activeCategory && (
              <section
                className={style.category}
                role="tabpanel"
              >
                <header className={style.categoryHeader}>
                  <div>
                    <h3>{activeCategory.categoryName}</h3>
                    <span>
                      {activeCategory.nodes.length}개 노드 후보
                    </span>
                  </div>
                </header>

                <div className={style.nodeList}>
                  {activeCategory.nodes.length === 0 ? (
                    <p className={style.emptyMessage}>
                      분류된 노드 후보가 없습니다.
                    </p>
                  ) : (
                    sortNodesByType(activeCategory.nodes).map(
                      (node) => (
                        <NodeCandidateItem
                          node={node}
                          categoryId={
                            activeCategory.categoryId
                          }
                          categories={categories}
                          isEditing={isEditing}
                          onTextChange={handleTextChange}
                          onTypeChange={handleTypeChange}
                          onCategoryChange={
                            handleCategoryChange
                          }
                          onDelete={handleDeleteNode}
                          key={node.candidateId}
                        />
                      ),
                    )
                  )}
                </div>
              </section>
            )}

            {hasInvalidNode && (
              <p className={style.errorMessage}>
                모든 노드 후보의 제목과 내용을 입력해 주세요.
              </p>
            )}
          </div>

          <footer className={style.footer}>
            <button
              className={style.closeButton}
              type="button"
              onClick={handleClose}
            >
              닫기
            </button>

            <button
              className={style.saveButton}
              type="submit"
              disabled={!hasNode || hasInvalidNode}
            >
              저장
            </button>
          </footer>
        </form>
      </section>
    </div>
  );
}
