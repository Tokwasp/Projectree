import { create } from "zustand";

export interface Notification {
  notificationId: number;
  type: "TREE_CREATED" | "MEETING_RECORD_CREATED";
  receiverId: number;
  message: string;
  createdAt: string;
}

interface NotificationState {
  notifications: Notification[];

  addNotification: (notification: Notification) => void;

  removeNotification: (notificationId: number) => void;

  clearNotifications: () => void;
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],

  addNotification: (notification) =>
    set((state) => ({
      notifications: [notification, ...state.notifications],
    })),

  removeNotification: (notificationId) =>
    set((state) => ({
      notifications: state.notifications.filter(
        (notification) => notification.notificationId !== notificationId,
      ),
    })),

  clearNotifications: () =>
    set({
      notifications: [],
    }),
}));
