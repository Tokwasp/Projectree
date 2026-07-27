export interface ProjectHomeSummary {
  projectId: number;
  title: string;
  description: string;
}

export interface RecentMeetingSummary {
  meetingId: number;
  title: string;
  scheduledAt: string;
  summary: string;
  hostName: string;
}

export interface RecentDecisionSummary {
  decisionId: number;
  title: string;
  sourceMeetingTitle: string;
  authorName: string;
  decidedAt: string;
}
