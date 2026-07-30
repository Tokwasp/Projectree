import { useState, type FormEvent } from "react";
import type { NodeCategory } from "../../api/categories";
import ProjectImageField from "./ProjectImageField";
import style from "../../css/project/ProjectCreateForm.module.css";

export interface ProjectCreateFormData {
  title: string;
  description: string;
  imageUrl: string;
  categoryIds: number[];
}

interface ProjectCreateFormProps {
  onCancel: () => void;
  onCreate: (formData: ProjectCreateFormData) => void;
  isCreating: boolean;
  categories: NodeCategory[];
  categoriesError: string | null;
  createError: string | null;
}

export default function ProjectCreateForm({
  onCancel,
  onCreate,
  isCreating,
  categories,
  categoriesError,
  createError,
}: ProjectCreateFormProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [selectedCategoryIds, setSelectedCategoryIds] = useState<number[]>([]);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmedTitle = title.trim();
    const trimmedDescription = description.trim();

    if (
      !trimmedTitle ||
      !trimmedDescription ||
      selectedCategoryIds.length === 0 ||
      isCreating
    ) {
      return;
    }

    onCreate({
      title: trimmedTitle,
      description: trimmedDescription,
      imageUrl,
      categoryIds: selectedCategoryIds,
    });
  };

  const handleCategoryChange = (categoryId: number) => {
    setSelectedCategoryIds((selectedIds) =>
      selectedIds.includes(categoryId)
        ? selectedIds.filter((id) => id !== categoryId)
        : [...selectedIds, categoryId],
    );
  };

  return (
    <section
      className={style.formContainer}
      aria-labelledby="project-create-title"
    >
      <form className={style.form} onSubmit={handleSubmit}>
        <div className={style.content}>
          <div className={style.formArea}>
            <h1
              className={style.title}
              id="project-create-title"
            >
              새 프로젝트 만들기
            </h1>

            <div className={style.field}>
              <label
                className={style.label}
                htmlFor="project-title"
              >
                프로젝트명
              </label>

              <input
                className={style.input}
                id="project-title"
                type="text"
                value={title}
                placeholder="프로젝트명을 입력하세요"
                maxLength={100}
                required
                onChange={(event) => setTitle(event.target.value)}
              />
            </div>

            <div className={style.field}>
              <label
                className={style.label}
                htmlFor="project-description"
              >
                소개
              </label>

              <textarea
                className={style.textarea}
                id="project-description"
                value={description}
                placeholder="프로젝트에 대한 간단한 소개를 입력하세요"
                maxLength={200}
                required
                onChange={(event) =>
                  setDescription(event.target.value)
                }
              />
            </div>

            <ProjectImageField
              imageUrl={imageUrl}
              onImageChange={setImageUrl}
            />

            <fieldset className={style.categoryField}>
              <legend className={style.label}>루트 노드</legend>

              <div className={style.categoryGrid}>
                {categoriesError && (
                  <p className={style.errorMessage} role="alert">
                    {categoriesError}
                  </p>
                )}

                {categories.map((category) => (
                  <label
                    className={style.categoryOption}
                    key={category.id}
                  >
                    <input
                      type="checkbox"
                      name="root-categories"
                      value={category.id}
                      checked={selectedCategoryIds.includes(category.id)}
                      onChange={() => handleCategoryChange(category.id)}
                    />

                    <span>{category.name}</span>
                  </label>
                ))}
              </div>
            </fieldset>

            {createError && (
              <p className={style.errorMessage} role="alert">
                {createError}
              </p>
            )}
          </div>

          <div
            className={style.guideArea}
            aria-label="노드 분류 안내 이미지 영역"
          >
            <p>노드 분류 안내 이미지</p>
          </div>
        </div>

        <div className={style.footer}>
          <button
            className={style.cancelButton}
            type="button"
            onClick={onCancel}
          >
            취소
          </button>

          <button
            className={style.createButton}
            type="submit"
            disabled={
              isCreating ||
              !title.trim() ||
              !description.trim() ||
              selectedCategoryIds.length === 0
            }
          >
            {isCreating ? "생성 중..." : "만들기"}
          </button>
        </div>
      </form>
    </section>
  );
}
