import { useState } from "react";
import projectPlaceholder from "../../assets/project-placeholder.svg";
import style from "../../css/project/ProjectImageField.module.css";

const DEFAULT_PROJECT_IMAGES = [
  {
    id: "project-placeholder",
    src: projectPlaceholder,
    alt: "프로젝트 기본 이미지",
  },
] as const;

interface ProjectImageFieldProps {
  imageUrl: string;
  onImageChange: (imageUrl: string) => void;
}

export default function ProjectImageField({
  imageUrl,
  onImageChange,
}: ProjectImageFieldProps) {
  const [isImageOptionsOpen, setIsImageOptionsOpen] = useState(false);

  const handleImageSelect = (selectedImageUrl: string) => {
    onImageChange(selectedImageUrl);
    setIsImageOptionsOpen(false);
  };

  return (
    <div className={style.field}>
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
          onClick={() =>
            setIsImageOptionsOpen((isOpen) => !isOpen)
          }
        >
          기본 이미지 선택
        </button>

        {imageUrl && (
          <button
            className={style.removeButton}
            type="button"
            onClick={() => onImageChange("")}
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
                imageUrl === image.src
                  ? style.imageOptionSelected
                  : ""
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
    </div>
  );
}
