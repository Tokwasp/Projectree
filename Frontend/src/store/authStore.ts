import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { LoginUser } from "../page/Auth/api/authApi";
import { clearProjectListCache } from "../page/Project/List/api/projectListApi";
import { disconnectMeeting } from "../utils/meetingSession";

interface AuthStore {
  memberId: number | null;
  name: string | null;
  imageUrl: string | null;

  login: (user: LoginUser) => void;
  logout: () => void;
  isLogin: () => boolean;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      memberId: null,
      name: null,
      imageUrl: null,

      login: ({ memberId, name, imageUrl }) =>
        set({ memberId, name, imageUrl }),

      logout: () => {
        disconnectMeeting();
        clearProjectListCache();
        set({ memberId: null, name: null, imageUrl: null });
        useAuthStore.persist.clearStorage();
      },

      isLogin: () => get().name !== null,
    }),
    {
      name: "auth-storage",
    },
  ),
);
