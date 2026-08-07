import { create } from "zustand";
import { useNotificationStore } from "./notificationStore";
import { toast } from "./toastStore";

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

      toast.info(notification.message, 3000);
    });

    eventSource.onerror = (e) => {
      console.error("SSE Error", e);

      eventSource.close();

      // 닫아버리므로 재연결이 없다 — 알림이 더 안 온다는 걸 알려야 한다.
      // connect()가 다시 불리기 전엔 여기 한 번만 들어온다
      if (get().connected) {
        toast.warning("실시간 알림 연결이 끊겼습니다. 새로고침해 주세요.", 5000);
      }

      set({
        eventSource: null,
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
