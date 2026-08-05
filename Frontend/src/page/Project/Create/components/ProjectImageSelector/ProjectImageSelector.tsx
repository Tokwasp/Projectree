import { useState, type ChangeEvent } from "react";
import { uploadImageToS3 } from "../../../../../api/s3Api";
import projectImage01 from "../../../../../assets/project-images/project_img01.png";
import projectImage02 from "../../../../../assets/project-images/project_img02.png";
import projectImage03 from "../../../../../assets/project-images/project_img03.png";
import projectImage04 from "../../../../../assets/project-images/project_img04.png";
import style from "./ProjectImageSelector.module.css";

const DEFAULT_PROJECT_IMAGES = [
  {
    id: "project-image-01",
    src: projectImage01,
    alt: "프로젝트 기본 이미지 1",
  },
  {
    id: "project-image-02",
    src: projectImage02,
    alt: "프로젝트 기본 이미지 2",
  },
  {
    id: "project-image-03",
    src: projectImage03,
    alt: "프로젝트 기본 이미지 3",
  },
  {
    id: "project-image-04",
    src: projectImage04,
    alt: "프로젝트 기본 이미지 4",
  },
] as const;

interface ProjectImageSelectorProps {
  imageUrl: string;
  onImageChange: (imageUrl: string) => void;
  onUploadingChange: (isUploading: boolean) => void;
}

export default function ProjectImageSelector({
  imageUrl,
  onImageChange,
  onUploadingChange,
}: ProjectImageSelectorProps) {
  const [uploadedImageUrl, setUploadedImageUrl] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");

  const handleDefaultImageSelect = (selectedImageUrl: string) => {
    onImageChange(selectedImageUrl);
    setUploadedImageUrl("");
    setUploadError("");
  };

  const handleImageClear = () => {
    onImageChange("");
    setUploadedImageUrl("");
    setUploadError("");
  };

  const handleImageUpload = async (
    event: ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";

    if (!file) {
      return;
    }

    if (!file.type.startsWith("image/")) {
      setUploadError("이미지 파일만 업로드할 수 있습니다.");
      return;
    }

    setIsUploading(true);
    onUploadingChange(true);
    setUploadError("");

    try {
      const uploadedUrl = await uploadImageToS3(file, "PROJECT");
      onImageChange(uploadedUrl);
      setUploadedImageUrl(uploadedUrl);
    } catch (error) {
      setUploadError(
        error instanceof Error
          ? error.message
          : "이미지 업로드에 실패했습니다.",
      );
    } finally {
      setIsUploading(false);
      onUploadingChange(false);
    }
  };

  return (
    <div className={style.imageField}>
      <div className={style.imageFieldHeader}>
        <span className={style.label}>대표 이미지</span>
        {imageUrl && (
          <button
            className={style.clearImageButton}
            type="button"
            onClick={handleImageClear}
          >
            선택 해제
          </button>
        )}
      </div>

      <div
        className={style.imageOptions}
        role="group"
        aria-label="프로젝트 대표 이미지 선택"
      >
        {DEFAULT_PROJECT_IMAGES.map((image) => (
          <button
            className={`${style.imageOption} ${
              imageUrl === image.src ? style.imageOptionSelected : ""
            }`}
            type="button"
            key={image.id}
            aria-pressed={imageUrl === image.src}
            onClick={() => handleDefaultImageSelect(image.src)}
          >
            <img className={style.optionImage} src={image.src} alt={image.alt} />
          </button>
        ))}

        <label
          className={`${style.uploadOption} ${
            uploadedImageUrl && imageUrl === uploadedImageUrl
              ? style.imageOptionSelected
              : ""
          } ${isUploading ? style.uploadOptionDisabled : ""}`}
        >
          <input
            className={style.uploadInput}
            type="file"
            accept="image/*"
            disabled={isUploading}
            onChange={handleImageUpload}
          />

          {uploadedImageUrl ? (
            <img
              className={style.optionImage}
              src={uploadedImageUrl}
              alt="업로드한 프로젝트 대표 이미지"
            />
          ) : (
            <span className={style.uploadContent}>
              <span className={style.uploadPlus} aria-hidden="true">
                +
              </span>
              <span>{isUploading ? "업로드 중" : "내 이미지"}</span>
            </span>
          )}
        </label>
      </div>

      {uploadError && (
        <p className={style.imageUploadError} role="alert">
          {uploadError}
        </p>
      )}
    </div>
  );
}
