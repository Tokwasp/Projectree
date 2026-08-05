import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import ProjectCreateAside from "../components/projectCreateAside/ProjectCreateAside";
import ProjectImageSelector from "../components/projectImageSelector/ProjectImageSelector";
import style from "../css/ProjectCreate.module.css";
import useCategories from "../hooks/useCategories";
import useCreateProject from "../hooks/useCreateProject";

export default function ProjectCreate() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const { categories, isLoading, error } = useCategories();
  const {
    createProject,
    isCreating,
    error: createError,
  } = useCreateProject();
  const [selectedCategoryIds, setSelectedCategoryIds] = useState<number[]>([]);

  const isSubmittable =
    Boolean(title.trim()) &&
    Boolean(description.trim()) &&
    selectedCategoryIds.length > 0 &&
    !isUploadingImage &&
    !isCreating;

  const selectedCategories = categories.filter((category) =>
    selectedCategoryIds.includes(category.id),
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!isSubmittable) {
      return;
    }

    const projectId = await createProject({
      title: title.trim(),
      content: description.trim(),
      photoUrl: imageUrl || null,
      categoryIds: selectedCategoryIds,
    });

    if (projectId !== null) {
      navigate("/projects");
    }
  };

  const handleCategoryChange = (categoryId: number) => {
    setSelectedCategoryIds((selectedIds) =>
      selectedIds.includes(categoryId)
        ? selectedIds.filter((selectedId) => selectedId !== categoryId)
        : [...selectedIds, categoryId],
    );
  };

  return (
    <section
      className={style.section}
      aria-labelledby="project-create-title"
    >
      <div className={style.workspace}>
        <div className={style.mainColumn}>
          <div className={style.heading}>
            <h1 className={style.title} id="project-create-title">
              새 프로젝트 만들기
            </h1>
            <p className={style.description}>
              프로젝트의 기본 정보와 시작 노드를 설정해주세요.
            </p>
          </div>

          <form className={style.form} onSubmit={handleSubmit}>
            <div className={style.formArea}>
              <section
                className={style.formSection}
                aria-labelledby="project-info-title"
              >
                <h2 className={style.sectionTitle} id="project-info-title">
                  기본 정보
                </h2>

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
                    maxLength={200}
                    required
                    onChange={(event) => setDescription(event.target.value)}
                  />
                </div>
              </section>

            <ProjectImageSelector
              imageUrl={imageUrl}
              onImageChange={setImageUrl}
              onUploadingChange={setIsUploadingImage}
            />

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

                      <span>{category.category}</span>
                    </label>
                  ))}
              </div>
              </fieldset>
            </div>

            <div className={style.footer}>
              {createError && (
                <p className={style.submitError} role="alert">
                  {createError}
                </p>
              )}

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
                {isCreating ? "생성 중..." : "만들기"}
              </button>
            </div>
          </form>
        </div>

        <ProjectCreateAside
          projectTitle={title}
          rootNodeNames={selectedCategories.map(
            (category) => category.category,
          )}
        />
      </div>
    </section>
  );
}
