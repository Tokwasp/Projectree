import { useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import {
  findMemberByEmail,
  inviteProjectMembers,
  type InviteResultsResponse,
  type MemberSearchResponse,
} from "../api/projectInvitationApi";

export default function useProjectInvitation() {
  const [isSearching, setIsSearching] = useState(false);
  const [isInviting, setIsInviting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const searchMember = async (
    email: string,
  ): Promise<MemberSearchResponse | null> => {
    setIsSearching(true);
    setError(null);

    try {
      return await findMemberByEmail(email);
    } catch (caughtError) {
      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "회원을 찾지 못했습니다.";

      setError(message);
      return null;
    } finally {
      setIsSearching(false);
    }
  };

  const inviteMembers = async (
    projectId: number,
    inviteeMemberIds: number[],
  ): Promise<InviteResultsResponse | null> => {
    setIsInviting(true);
    setError(null);

    try {
      return await inviteProjectMembers(projectId, {
        inviteeMemberIds,
      });
    } catch (caughtError) {
      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "팀원 초대에 실패했습니다.";

      setError(message);
      return null;
    } finally {
      setIsInviting(false);
    }
  };

  const clearError = () => {
    setError(null);
  };

  return {
    searchMember,
    inviteMembers,
    isSearching,
    isInviting,
    error,
    clearError,
  };
}