import { apiRequest } from "../../../../api/apiClient";

export interface MeetingRecordListItemResponse {
  meetingRecordId: number;
  meetingId: number;
  title: string;
  meetingDate: string;
  startedAt: string;
  createdAt: string;
  updatedAt: string;
}

export interface MeetingRecordPageResponse {
  records: MeetingRecordListItemResponse[];
  page: number;
  size: number;
  totalElements: number;
  totalPages: number;
}

export const getMeetingRecords = (
  projectId: number,
  page = 0,
  size = 10,
): Promise<MeetingRecordPageResponse> =>
  apiRequest<MeetingRecordPageResponse>(
    `/projects/${projectId}/meetings/records?page=${page}&size=${size}`,
  );

export interface MeetingRecordDetailResponse {
  meetingRecordId: number;
  projectId: number;
  meetingId: number;
  title: string;
  meetingDate: string;
  startedAt: string;
  endedAt: string;
  durationMinutes: number;
  summary: string[];
  decisions: string[];
  nextTodos: string[];
  issues: string[];
  version: number;
  createdAt: string;
  updatedAt: string;
}

export const getMeetingRecordDetail = (
  projectId: number,
  meetingId: number,
): Promise<MeetingRecordDetailResponse> =>
  apiRequest<MeetingRecordDetailResponse>(
    `/projects/${projectId}/meetings/${meetingId}/record`,
  );
