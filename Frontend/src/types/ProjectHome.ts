export interface ProjectHomeSummary {
  projectId: number;
  title: string;
  description: string;
  createdAt: string;
  memberCount: number;
}

export interface RecentMeetingSummary {
  meetingId: number;
  title: string;
  scheduledAt: string;
  summary: string;
  hostName: string;
}

export interface AiFeedbackSummary {
  details: {
    label: string;
    description: string;
  }[];
}

export interface SpeakingTimeSummary {
  memberId: number;
  name: string;
  percentage: number;
  isCurrentUser: boolean;
}
