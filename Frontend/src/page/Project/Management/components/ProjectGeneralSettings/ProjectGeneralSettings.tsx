import { useState } from "react";
import ProjectImageSelector from "../../../Create/components/ProjectImageSelector/ProjectImageSelector";
import useUpdateProject from "../../hooks/useUpdateProject";
import style from "./ProjectGeneralSettings.module.css";

interface ProjectGeneralSettingsProps {
  projectId: number | null;
  isOwner: boolean;
  projectName?: string;
  projectContent?: string;
  projectImage?: string;
  isProjectLoading: boolean;
  isProjectHomeLoading: boolean;
  onTitleUpdated: (title: string) => void;
}

export default function ProjectGeneralSettings({
  projectId,
  isOwner,
  projectName,
  projectContent,
  projectImage,
  isProjectLoading,
  isProjectHomeLoading,
  onTitleUpdated,
}: ProjectGeneralSettingsProps) {
  const [editingField, setEditingField] = useState<
    "image" | "title" | "content" | null
  >(null);
  const [titleInput, setTitleInput] = useState("");
  const [contentInput, setContentInput] = useState("");
  const [imageInput, setImageInput] = useState("");
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [updatedTitle, setUpdatedTitle] = useState<string | null>(null);
  const [updatedContent, setUpdatedContent] = useState<string | null>(null);
  const [updatedImage, setUpdatedImage] = useState<string | null>(null);
  const {
    updateTitle,
    updateContent,
    updateImage,
    isUpdating,
    error,
    clearError,
  } = useUpdateProject();

  const displayedTitle = updatedTitle ?? projectName;
  const displayedContent = updatedContent ?? projectContent;
  const displayedImage = updatedImage ?? projectImage;
  const projectInitial = displayedTitle?.trim().charAt(0) || "P";

  const handleStartEdit = (field: "image" | "title" | "content") => {
    if (!isOwner) {
      return;
    }

    clearError();
    setEditingField(field);

    if (field === "image") {
      setImageInput(displayedImage ?? "");
    }

    if (field === "title") {
      setTitleInput(displayedTitle ?? "");
    }

    if (field === "content") {
      setContentInput(displayedContent ?? "");
    }
  };

  const handleCancelEdit = () => {
    if (isUpdating || isUploadingImage) {
      return;
    }

    clearError();
    setEditingField(null);
  };

  const handleSaveTitle = async () => {
    if (projectId === null || !titleInput.trim()) {
      return;
    }

    const title = titleInput.trim();
    const isCompleted = await updateTitle(projectId, title);

    if (isCompleted) {
      setUpdatedTitle(title);
      onTitleUpdated(title);
      setEditingField(null);
    }
  };

  const handleSaveContent = async () => {
    if (projectId === null || !contentInput.trim()) {
      return;
    }

    const content = contentInput.trim();
    const isCompleted = await updateContent(projectId, content);

    if (isCompleted) {
      setUpdatedContent(content);
      setEditingField(null);
    }
  };

  const handleSaveImage = async () => {
    if (projectId === null || !imageInput) {
      return;
    }

    const isCompleted = await updateImage(projectId, imageInput);

    if (isCompleted) {
      setUpdatedImage(imageInput);
      setEditingField(null);
    }
  };

  return (
    <section className={style.card}>
      <div className={style.cardHeader}>
        <h2 className={style.cardTitle}>일반 설정</h2>
        <p className={style.cardDescription}>프로젝트의 대표 정보입니다.</p>
      </div>

      <div className={style.settingList}>
        <div className={style.photoSetting}>
          <div>
            <h3 className={style.settingLabel}>프로젝트 사진</h3>
            <p className={style.settingDescription}>
              프로젝트를 구분할 수 있는 대표 이미지입니다.
            </p>
          </div>

          <div className={style.photoControl}>
            <div className={style.projectImage} aria-hidden="true">
              {displayedImage ? (
                <img src={displayedImage} alt="" />
              ) : (
                projectInitial
              )}
            </div>
            <button
              className={style.secondaryButton}
              type="button"
              disabled={!isOwner || isUpdating}
              onClick={() => handleStartEdit("image")}
            >
              사진 변경
            </button>
          </div>
        </div>

        {editingField === "image" && (
          <div className={style.imageEditor}>
            <ProjectImageSelector
              imageUrl={imageInput}
              onImageChange={setImageInput}
              onUploadingChange={setIsUploadingImage}
            />
            {error && (
              <p className={style.updateError} role="alert">
                {error}
              </p>
            )}
            <div className={style.editActions}>
              <button
                className={style.cancelEditButton}
                type="button"
                disabled={isUpdating || isUploadingImage}
                onClick={handleCancelEdit}
              >
                취소
              </button>
              <button
                className={style.saveButton}
                type="button"
                disabled={isUpdating || isUploadingImage || !imageInput}
                onClick={() => void handleSaveImage()}
              >
                {isUpdating ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        )}

        <div className={style.settingItem}>
          <div>
            <h3 className={style.settingLabel}>프로젝트 이름</h3>
            <p className={style.settingDescription}>
              프로젝트에 표시되는 이름입니다.
            </p>
          </div>

          <div className={style.settingControl}>
            {editingField === "title" ? (
              <div className={style.editControl}>
                <input
                  className={style.textInput}
                  aria-label="프로젝트 이름"
                  type="text"
                  maxLength={100}
                  value={titleInput}
                  onChange={(event) => setTitleInput(event.target.value)}
                />
                <div className={style.editActions}>
                  <button
                    className={style.cancelEditButton}
                    type="button"
                    disabled={isUpdating}
                    onClick={handleCancelEdit}
                  >
                    취소
                  </button>
                  <button
                    className={style.saveButton}
                    type="button"
                    disabled={isUpdating || !titleInput.trim()}
                    onClick={() => void handleSaveTitle()}
                  >
                    {isUpdating ? "저장 중..." : "저장"}
                  </button>
                </div>
              </div>
            ) : (
              <>
                <span className={style.settingValue}>
                  {isProjectLoading
                    ? "불러오는 중..."
                    : (displayedTitle ?? "-")}
                </span>
                <button
                  className={style.secondaryButton}
                  type="button"
                  disabled={!isOwner || isUpdating}
                  onClick={() => handleStartEdit("title")}
                >
                  변경
                </button>
              </>
            )}
          </div>
        </div>

        {editingField === "title" && error && (
          <p className={style.updateError} role="alert">
            {error}
          </p>
        )}

        <div className={style.settingItem}>
          <div>
            <h3 className={style.settingLabel}>프로젝트 설명</h3>
            <p className={style.settingDescription}>
              프로젝트의 목표와 내용을 소개합니다.
            </p>
          </div>

          <div className={style.settingControl}>
            {editingField === "content" ? (
              <div className={style.editControl}>
                <textarea
                  className={style.textArea}
                  aria-label="프로젝트 설명"
                  maxLength={200}
                  rows={3}
                  value={contentInput}
                  onChange={(event) => setContentInput(event.target.value)}
                />
                <div className={style.editActions}>
                  <button
                    className={style.cancelEditButton}
                    type="button"
                    disabled={isUpdating}
                    onClick={handleCancelEdit}
                  >
                    취소
                  </button>
                  <button
                    className={style.saveButton}
                    type="button"
                    disabled={isUpdating || !contentInput.trim()}
                    onClick={() => void handleSaveContent()}
                  >
                    {isUpdating ? "저장 중..." : "저장"}
                  </button>
                </div>
              </div>
            ) : (
              <>
                <span className={style.settingValue}>
                  {isProjectHomeLoading
                    ? "불러오는 중..."
                    : (displayedContent ?? "-")}
                </span>
                <button
                  className={style.secondaryButton}
                  type="button"
                  disabled={!isOwner || isUpdating}
                  onClick={() => handleStartEdit("content")}
                >
                  변경
                </button>
              </>
            )}
          </div>
        </div>

        {editingField === "content" && error && (
          <p className={style.updateError} role="alert">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}
