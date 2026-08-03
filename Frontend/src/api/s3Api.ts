import { ApiError, apiRequest } from "./apiClient";

export type S3UploadType = "PROFILE" | "PROJECT";

export interface PresignedUrlResponse {
  presignedUrl: string;
  imageUrl: string;
}

const getPresignedUrl = (type: S3UploadType) =>
  apiRequest<PresignedUrlResponse>(`/s3/presigned-url?type=${type}`);

export const uploadImageToS3 = async (
  file: File,
  type: S3UploadType,
): Promise<string> => {
  const { presignedUrl, imageUrl } = await getPresignedUrl(type);

  const response = await fetch(presignedUrl, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });

  if (!response.ok) {
    throw new ApiError(
      "S3_UPLOAD_FAILED",
      "이미지 업로드에 실패했습니다.",
      response.status,
    );
  }

  return imageUrl;
};
