import { apiRequest } from "../../../../api/apiClient";

export interface MeetingRecordResponse {
  name: string;
  currentPageNum: number;
  totalElements: number;
}

export interface PersonalSpeakingResponse {
  name: string;
  speakPercent: number;
}

export interface MyMeetingReviewResponse {
  speedFeedback: string;
  personalFeedback: string;
  overallFeedback: string;
}

export interface ProjectHomeResponse {
  meetingRecordList: MeetingRecordResponse[] | null;
  personalSpeakingList: PersonalSpeakingResponse[];
  myReview: MyMeetingReviewResponse | null;
}

export const getProjectHome = (
  projectId: number,
  page = 0,
  size = 10,
): Promise<ProjectHomeResponse> =>
  apiRequest<ProjectHomeResponse>(
    `/projects/${projectId}/home?page=${page}&size=${size}`,
  );