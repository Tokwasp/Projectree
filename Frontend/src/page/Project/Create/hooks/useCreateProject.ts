import { useState } from "react";
import {
  createProject as requestCreateProject,
  type ProjectCreateRequest,
} from "../api/projectApi";
import { ApiError } from "../../../../api/apiClient";
import { addProjectToListCache } from "../../List/api/projectListApi";
import { toast } from "../../../../store/toastStore";

export default function useCreateProject() {
  const [isCreating, setIsCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createProject = async (
    request: ProjectCreateRequest,
  ): Promise<number | null> => {
    setIsCreating(true);
    setError(null);

    try {
      const projectId = await requestCreateProject(request);

      addProjectToListCache({
        projectId,
        title: request.title,
        photoUrl: request.photoUrl,
        memberCnt: 1,
      });

      // 생성 직후 목록으로 넘어가서 이 화면이 사라진다 — 결과는 토스트로만 남는다
      toast.success("프로젝트를 만들었습니다.");

      return projectId;
    } catch (caughtError) {
      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "프로젝트 생성에 실패했습니다.";

      setError(message);
      // 이 error를 화면에 그리는 곳이 없다 — 토스트가 유일한 통보 수단이다
      toast.error(message);
      return null;
    } finally {
      setIsCreating(false);
    }
  };

  return {
    createProject,
    isCreating,
    error,
  };
}
