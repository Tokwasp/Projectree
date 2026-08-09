import { useEffect, useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import {
  getMeetingRecords,
  type MeetingRecordPageResponse,
} from "../api/meetingRecordApi";

export default function useMeetingRecords(
  projectId: number | null,
  page: number,
  size = 10,
) {
  const [data, setData] = useState<MeetingRecordPageResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (projectId === null) {
      return;
    }

    let isCancelled = false;

    const fetchMeetingRecords = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await getMeetingRecords(projectId, page, size);

        if (!isCancelled) {
          setData(response);
        }
      } catch (caughtError) {
        const message =
          caughtError instanceof ApiError
            ? caughtError.message
            : "회의록 목록을 불러오지 못했습니다.";

        if (!isCancelled) {
          setData(null);
          setError(message);
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void fetchMeetingRecords();

    return () => {
      isCancelled = true;
    };
  }, [page, projectId, size]);

  return {
    data: projectId === null ? null : data,
    isLoading: projectId === null ? false : isLoading,
    error:
      projectId === null
        ? "올바르지 않은 프로젝트입니다."
        : error,
  };
}