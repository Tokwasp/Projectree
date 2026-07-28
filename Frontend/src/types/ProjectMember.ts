export interface ProjectMemberSummary {
  projectMemberId: number;
  userId: number;
  name: string;
  email: string;
  profileImageUrl: string | null;
  status: string;
  joinedAt: string;
  leftAt: string | null;
}