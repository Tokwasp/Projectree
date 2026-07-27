export interface UserProfile {
  userId: number;
  name: string;
  email: string;
  profileImageUrl?: string;
}

export interface UserProjectSummary {
  projectId: number;
  title: string;
  role: string;
  joinedAt: string;
  lastActivityAt: string;
  thumbnailUrl?: string;
}