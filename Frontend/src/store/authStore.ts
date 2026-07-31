import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { LoginUser } from "../page/Auth/api/authApi";
import { disconnectMeeting } from "../utils/meetingSession";

interface AuthStore {
  name: string | null;
  imageUrl: string | null;

  login: (user: LoginUser) => void;
  logout: () => void;
  isLogin: () => boolean;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      name: null,
      imageUrl: null,

      login: ({ name, imageUrl }) => set({ name, imageUrl }),

      logout: () => {
        disconnectMeeting();
        set({ name: null, imageUrl: null });
        useAuthStore.persist.clearStorage();
      },

      isLogin: () => get().name !== null,
    }),
    {
      name: "auth-storage",
    },
  ),
);
