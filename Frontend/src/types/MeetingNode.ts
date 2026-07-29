export type NodeCandidateType =
  | "DECISION"
  | "ACTION"
  | "ISSUE";

export interface NodeCandidate {
  candidateId: string;
  type: NodeCandidateType;
  title: string;
  content: string;
}

export interface NodeCategoryResult {
  categoryId: number;
  categoryName: string;
  nodes: NodeCandidate[];
}

export interface MeetingNodeResult {
  meetingId: number;
  meetingTitle: string;
  categories: NodeCategoryResult[];
}