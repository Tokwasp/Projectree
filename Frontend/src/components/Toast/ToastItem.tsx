import { useEffect, useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { ToastData, ToastType } from "../../store/toastStore";

const EXIT_MS = 240;

const ICONS: Record<ToastType, typeof Info> = {
  success: CheckCircle2,
  error: XCircle,
  warning: AlertTriangle,
  info: Info,
};

interface ToastItemProps {
  toast: ToastData;
  styles: Record<string, string>;
  onClose: (id: number) => void;
}

export default function ToastItem({ toast, styles, onClose }: ToastItemProps) {
  const [isLeaving, setIsLeaving] = useState(false);
  const closedRef = useRef(false);
  const Icon = ICONS[toast.type];

  const close = () => {
    if (closedRef.current) return;
    closedRef.current = true;
    setIsLeaving(true);
    window.setTimeout(() => onClose(toast.id), EXIT_MS);
  };

  useEffect(() => {
    const timer = window.setTimeout(close, toast.duration);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className={`${styles.toast} ${styles[toast.type]} ${isLeaving ? styles.leaving : ""}`}
      role="alert"
    >
      <span className={styles.icon}>
        <Icon size={20} />
      </span>
      <span className={styles.message}>{toast.message}</span>
      <button
        type="button"
        className={styles.closeBtn}
        onClick={close}
        aria-label="알림 닫기"
      >
        <X size={16} />
      </button>
    </div>
  );
}
