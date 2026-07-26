import { useState, type FormEvent } from "react";
import style from "../../css/project/ProjectCreateModal.module.css";

const ROOT_CATEGORIES = [
  "Frontend",
  "Backend",
  "Design",
  "Planning",
  "AI",
  "Infrastructure",
] as const;

type RootCategory = (typeof ROOT_CATEGORIES)[number];

export interface ProjectCreateFormData {
  title: string;
  description: string;
  rootCategories: RootCategory[];
}

interface ProjectCreateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreate: (formData: ProjectCreateFormData) => void;
}

export default function ProjectCreateModal({
  isOpen,
  onClose,
  onCreate,
}: ProjectCreateModalProps) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [rootCategories, setRootCategories] = useState<RootCategory[]>([]);

  if (!isOpen) {
    return null;
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmedTitle = title.trim();

    if (!trimmedTitle || rootCategories.length === 0) {
      return;
    }

    onCreate({
      title: trimmedTitle,
      description: description.trim(),
      rootCategories,
    });
  };

  const handleCategoryChange = (category: RootCategory) => {
    setRootCategories((selectedCategories) =>
      selectedCategories.includes(category)
        ? selectedCategories.filter(
            (selectedCategory) => selectedCategory !== category,
          )
        : [...selectedCategories, category],
    );
  };

  return (
    <div className={style.backdrop}>
      <section
        className={style.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="project-create-title"
      >
        <form className={style.form} onSubmit={handleSubmit}>
          <div className={style.content}>
            <div className={style.formArea}>
              <h2
                className={style.title}
                id="project-create-title"
              >
                새 프로젝트 만들기
              </h2>

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
                  onChange={(event) =>
                    setTitle(event.target.value)
                  }
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
                  maxLength={500}
                  onChange={(event) =>
                    setDescription(event.target.value)
                  }
                />
              </div>

              <fieldset className={style.categoryField}>
                <legend className={style.label}>
                  루트 노드
                </legend>

                <div className={style.categoryGrid}>
                  {ROOT_CATEGORIES.map((category) => (
                    <label
                      className={style.categoryOption}
                      key={category}
                    >
                      <input
                        type="checkbox"
                        name="root-categories"
                        value={category}
                        checked={rootCategories.includes(category)}
                        onChange={() => handleCategoryChange(category)}
                      />

                      <span>{category}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
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
              onClick={onClose}
            >
              취소
            </button>

            <button
              className={style.createButton}
              type="submit"
              disabled={!title.trim() || rootCategories.length === 0}
            >
              만들기
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
