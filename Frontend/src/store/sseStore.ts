import { create } from "zustand";
import { useNotificationStore } from "./notificationStore";

interface SseState {
  eventSource: EventSource | null;
  connected: boolean;

  connect: () => void;
  disconnect: () => void;
}

export const useSseStore = create<SseState>((set, get) => ({
  eventSource: null,
  connected: false,

  connect: () => {
    if (get().eventSource) return;

    const eventSource = new EventSource(
      `${import.meta.env.VITE_BASE_URL}/notifications/subscribe`,
      {
        withCredentials: true,
      },
    );

    eventSource.addEventListener("connect", () => {
      console.log("SSE 연결 성공");
      set({ connected: true });
    });

    eventSource.addEventListener("notification", (event) => {
      const notification = JSON.parse(event.data);

      useNotificationStore.getState().addNotification(notification);
    });

    eventSource.onerror = (e) => {
      console.error("SSE Error", e);

      set({
        connected: false,
      });
    };

    set({
      eventSource,
    });
  },

  disconnect: () => {
    get().eventSource?.close();

    set({
      eventSource: null,
      connected: false,
    });
  },
}));
