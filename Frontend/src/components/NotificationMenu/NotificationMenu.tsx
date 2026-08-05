import { useState } from "react";
import NotificationIcon from "../../assets/icons/header/notification.png";
import { useNotificationStore } from "../../store/notificationStore";
import style from "./NotificationMenu.module.css";

const formatCreatedAt = (createdAt: string) => {
  const date = new Date(createdAt);

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  return new Intl.DateTimeFormat("ko-KR", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
};

export default function NotificationMenu() {
  const [isOpen, setIsOpen] = useState(false);
  const notifications = useNotificationStore(
    (state) => state.notifications,
  );
  const removeNotification = useNotificationStore(
    (state) => state.removeNotification,
  );
  const clearNotifications = useNotificationStore(
    (state) => state.clearNotifications,
  );

  const notificationCount =
    notifications.length > 99 ? "99+" : notifications.length;

  return (
    <div
      className={style.wrapper}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          setIsOpen(false);
        }
      }}
    >
      <button
        className={style.trigger}
        type="button"
        aria-label={`알림 ${notifications.length}개`}
        aria-expanded={isOpen}
        aria-controls="notification-menu"
        onClick={() => setIsOpen((current) => !current)}
      >
        <img
          className={style.icon}
          src={NotificationIcon}
          alt=""
          aria-hidden="true"
        />

        {notifications.length > 0 && (
          <span className={style.badge} aria-hidden="true">
            {notificationCount}
          </span>
        )}
      </button>

      {isOpen && (
        <section
          className={style.menu}
          id="notification-menu"
          aria-labelledby="notification-title"
        >
          <div className={style.header}>
            <h2 className={style.title} id="notification-title">
              알림
            </h2>

            {notifications.length > 0 && (
              <button
                className={style.clearButton}
                type="button"
                onClick={clearNotifications}
              >
                전체 삭제
              </button>
            )}
          </div>

          {notifications.length === 0 ? (
            <p className={style.emptyMessage}>
              새로운 알림이 없습니다.
            </p>
          ) : (
            <ul className={style.list}>
              {notifications.map((notification) => (
                <li
                  className={style.item}
                  key={notification.notificationId}
                >
                  <div className={style.itemContent}>
                    <p className={style.message}>
                      {notification.message}
                    </p>
                    <time
                      className={style.createdAt}
                      dateTime={notification.createdAt}
                    >
                      {formatCreatedAt(notification.createdAt)}
                    </time>
                  </div>

                  <button
                    className={style.removeButton}
                    type="button"
                    aria-label="알림 삭제"
                    onClick={() =>
                      removeNotification(notification.notificationId)
                    }
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}