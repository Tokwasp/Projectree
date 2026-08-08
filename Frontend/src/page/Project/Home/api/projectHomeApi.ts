import { apiRequest } from "../../../../api/apiClient";

export interface ProjectDetailResponse {
  projectTitle: string;
  projectContent: string;
  participantCount: number;
  projectCreatedAt: string;
}

export interface MeetingRecordResponse {
  meetingId: number;
  name: string;
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
  projectDetail: ProjectDetailResponse;
  meetingRecordList: MeetingRecordResponse[];
  personalSpeakingList: PersonalSpeakingResponse[];
  myReview: MyMeetingReviewResponse | null;
}

export const getProjectHome = (
  projectId: number,
): Promise<ProjectHomeResponse> =>
  apiRequest<ProjectHomeResponse>(
    `/projects/${projectId}/home`,
  );
