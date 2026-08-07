import { useToastStore } from "../../store/toastStore";
import ToastItem from "./ToastItem";
import styles from "./Toast.module.css";

export default function ToastViewport() {
  const toasts = useToastStore((state) => state.toasts);
  const removeToast = useToastStore((state) => state.removeToast);

  if (toasts.length === 0) return null;

  return (
    <div className={styles.viewport}>
      {toasts.map((toast) => (
        <ToastItem
          key={toast.id}
          toast={toast}
          styles={styles}
          onClose={removeToast}
        />
      ))}
    </div>
  );
}
