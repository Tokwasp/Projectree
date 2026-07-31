import { useEffect, useState } from "react";
import { ApiError } from "../../../../api/apiClient";
import {
  acceptInvitation as requestAcceptInvitation,
  getInvitation,
  type InvitationLandingResponse,
} from "../api/invitationApi";

export default function useInvitationLanding(token: string | null) {
  const [invitation, setInvitation] =
    useState<InvitationLandingResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isAccepting, setIsAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (token === null) {
      return;
    }

    let isCancelled = false;

    const fetchInvitation = async () => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await getInvitation(token);

        if (!isCancelled) {
          setInvitation(response);
        }
      } catch (caughtError) {
        if (!isCancelled) {
          const message =
            caughtError instanceof ApiError
              ? caughtError.message
              : "초대 정보를 불러오지 못했습니다.";

          setError(message);
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void fetchInvitation();

    return () => {
      isCancelled = true;
    };
  }, [token]);

  const acceptInvitation = async (): Promise<number | null> => {
    if (token === null) {
      return null;
    }

    setIsAccepting(true);
    setError(null);

    try {
      const response = await requestAcceptInvitation(token);
      return response.projectId;
    } catch (caughtError) {
      const message =
        caughtError instanceof ApiError
          ? caughtError.message
          : "초대를 수락하지 못했습니다.";

      setError(message);
      return null;
    } finally {
      setIsAccepting(false);
    }
  };

  return {
    invitation: token === null ? null : invitation,
    isLoading: token === null ? false : isLoading,
    isAccepting,
    error:
      token === null
        ? "유효하지 않은 초대 링크입니다."
        : error,
    acceptInvitation,
  };
}