import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import projectPlaceholder from "../../../../assets/project-placeholder.svg";
import style from "../css/ProjectCreate.module.css";
import useCategories from "../hooks/useCategories";

const DEFAULT_PROJECT_IMAGES = [
  {
    id: "project-placeholder",
    src: projectPlaceholder,
    alt: "프로젝트 기본 이미지",
  },
] as const;

export default function ProjectCreate() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const { categories, isLoading, error } = useCategories();
  const [selectedCategoryIds, setSelectedCategoryIds] = useState<number[]>([]);
  const [isImageOptionsOpen, setIsImageOptionsOpen] = useState(false);
  const [isPromptOpen, setIsPromptOpen] = useState(false);
  const [imagePrompt, setImagePrompt] = useState("");

  const isSubmittable =
    Boolean(title.trim()) && selectedCategoryIds.length > 0;

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
  };

  const handleCategoryChange = (categoryId: number) => {
    setSelectedCategoryIds((selectedIds) =>
      selectedIds.includes(categoryId)
        ? selectedIds.filter((selectedId) => selectedId !== categoryId)
        : [...selectedIds, categoryId],
    );
  };

  const handleImageSelect = (selectedImageUrl: string) => {
    setImageUrl(selectedImageUrl);
    setIsImageOptionsOpen(false);
  };

  return (
    <section
      className={style.formContainer}
      aria-labelledby="project-create-title"
    >
      <form className={style.form} onSubmit={handleSubmit}>
        <div className={style.content}>
          <div className={style.formArea}>
            <h1 className={style.title} id="project-create-title">
              새 프로젝트 만들기
            </h1>

            <div className={style.field}>
              <label className={style.label} htmlFor="project-title">
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
              <label className={style.label} htmlFor="project-description">
                소개
              </label>

              <textarea
                className={style.textarea}
                id="project-description"
                value={description}
                placeholder="프로젝트에 대한 간단한 소개를 입력하세요"
                maxLength={500}
                onChange={(event) => setDescription(event.target.value)}
              />
            </div>

            <div className={style.imageField}>
              <span className={style.label}>대표 이미지</span>

              <div className={style.preview}>
                {imageUrl ? (
                  <img
                    className={style.previewImage}
                    src={imageUrl}
                    alt="선택한 프로젝트 대표 이미지 미리보기"
                  />
                ) : (
                  <span className={style.previewPlaceholder}>
                    프로젝트 대표 이미지를 선택해주세요
                  </span>
                )}
              </div>

              <div className={style.buttonGroup}>
                <button
                  className={style.selectButton}
                  type="button"
                  aria-expanded={isImageOptionsOpen}
                  onClick={() => setIsImageOptionsOpen((isOpen) => !isOpen)}
                >
                  기본 이미지 선택
                </button>

                <button
                  className={style.generateToggleButton}
                  type="button"
                  aria-expanded={isPromptOpen}
                  onClick={() => setIsPromptOpen((isOpen) => !isOpen)}
                >
                  AI 이미지 생성
                </button>

                {imageUrl && (
                  <button
                    className={style.removeButton}
                    type="button"
                    onClick={() => setImageUrl("")}
                  >
                    이미지 제거
                  </button>
                )}
              </div>

              {isImageOptionsOpen && (
                <div
                  className={style.imageOptions}
                  role="group"
                  aria-label="프로젝트 기본 이미지 선택"
                >
                  {DEFAULT_PROJECT_IMAGES.map((image) => (
                    <button
                      className={`${style.imageOption} ${
                        imageUrl === image.src ? style.imageOptionSelected : ""
                      }`}
                      type="button"
                      key={image.id}
                      aria-pressed={imageUrl === image.src}
                      onClick={() => handleImageSelect(image.src)}
                    >
                      <img
                        className={style.optionImage}
                        src={image.src}
                        alt={image.alt}
                      />
                    </button>
                  ))}
                </div>
              )}

              {isPromptOpen && (
                <div className={style.promptArea}>
                  <label
                    className={style.label}
                    htmlFor="project-image-prompt"
                  >
                    생성할 이미지 설명
                  </label>

                  <div className={style.promptControls}>
                    <input
                      className={style.promptInput}
                      id="project-image-prompt"
                      type="text"
                      value={imagePrompt}
                      placeholder="예: 보라색 계열의 협업 프로젝트 이미지"
                      maxLength={300}
                      onChange={(event) => setImagePrompt(event.target.value)}
                    />

                    <button
                      className={style.generateButton}
                      type="button"
                      disabled={!imagePrompt.trim()}
                    >
                      생성
                    </button>
                  </div>
                </div>
              )}
            </div>

            <fieldset className={style.categoryField}>
              <legend className={style.label}>루트 노드</legend>

              <div className={style.categoryGrid}>
                {isLoading && (
                  <p className={style.categoryMessage}>
                    카테고리를 불러오는 중입니다.
                  </p>
                )}

                {error && (
                  <p className={style.categoryError} role="alert">
                    {error}
                  </p>
                )}

                {!isLoading &&
                  !error &&
                  categories.map((category) => (
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
            onClick={() => navigate(-1)}
          >
            취소
          </button>

          <button
            className={style.createButton}
            type="submit"
            disabled={!isSubmittable}
          >
            만들기
          </button>
        </div>
      </form>
    </section>
  );
}
