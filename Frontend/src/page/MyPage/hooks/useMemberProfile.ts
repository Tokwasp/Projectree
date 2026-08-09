import { useEffect, useState } from "react";
import { apiErrorMessage } from "../../../api/apiClient";
import {
  getCachedMemberProfile,
  getMemberProfile,
  type MemberProfileResponse,
} from "../api/memberProfileApi";

export default function useMemberProfile() {
  const [profile, setProfile] = useState<MemberProfileResponse | null>(() =>
    getCachedMemberProfile(),
  );
  const [isLoading, setIsLoading] = useState(
    () => getCachedMemberProfile() === null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;

    const fetchMemberProfile = async () => {
      setIsLoading(getCachedMemberProfile() === null);
      setError(null);

      try {
        const response = await getMemberProfile();

        if (!isCancelled) {
          setProfile(response);
        }
      } catch (caughtError) {
        if (!isCancelled) {
          setProfile(null);
          setError(
            apiErrorMessage(caughtError, "회원 정보를 불러오지 못했습니다."),
          );
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    };

    void fetchMemberProfile();

    return () => {
      isCancelled = true;
    };
  }, []);

  return {
    profile,
    isLoading,
    error,
  };
}
