import { useEffect, useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import {
  getMeetingRecordDetail,
  type MeetingRecordDetailResponse,
} from "../api/meetingRecordApi";

export default function useMeetingRecordDetail(
  projectId: number | null,
  meetingId: number | null,
) {
  const [data, setData] =
    useState<MeetingRecordDetailResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (projectId === null || meetingId === null) {
      return;
    }

    let isCancelled = false;

    const fetchMeetingRecordDetail = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await getMeetingRecordDetail(
          projectId,
          meetingId,
        );

        if (!isCancelled) {
          setData(response);
        }
      } catch (caughtError) {
        const message =
          caughtError instanceof ApiError
            ? caughtError.message
            : "회의록을 불러오지 못했습니다.";

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

    void fetchMeetingRecordDetail();

    return () => {
      isCancelled = true;
    };
  }, [meetingId, projectId]);

  const hasInvalidParams =
    projectId === null || meetingId === null;

  return {
    data: hasInvalidParams ? null : data,
    isLoading: hasInvalidParams ? false : isLoading,
    error: hasInvalidParams
      ? "올바르지 않은 회의록 주소입니다."
      : error,
  };
}