import { useEffect } from "react";
import style from "./LoginModal.module.css";
import { useLoginModalStore } from "../../store/loginModalStore";
import { useSocialLogin } from "../../page/Auth/hooks/useSocialLogin";

export default function LoginModal() {
  const { isOpen, closeLoginModal } = useLoginModalStore();
  const { loginWithNaver, loginWithGoogle } = useSocialLogin();

  // ESC 키로 닫기
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeLoginModal();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, closeLoginModal]);

  if (!isOpen) return null;

  return (
    <div
      className={style.overlay}
      onClick={closeLoginModal}
      role="presentation"
    >
      <div
        className={style.modal}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="login-modal-title"
      >
        <button
          type="button"
          className={style.closeBtn}
          onClick={closeLoginModal}
          aria-label="닫기"
        >
          &times;
        </button>

        <div id="login-modal-title" className={style.title}>
          로그인
        </div>
        <p className={style.subtitle}>간편하게 시작하세요</p>

        <div className={style.buttons}>
          <button
            type="button"
            className={`${style.socialBtn} ${style.googleBtn}`}
            onClick={() => loginWithGoogle()}
          >
            <GoogleIcon />
            <span>Google로 계속하기</span>
          </button>

          <button
            type="button"
            className={`${style.socialBtn} ${style.naverBtn}`}
            onClick={() => loginWithNaver()}
          >
            <NaverIcon />
            <span>네이버로 계속하기</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

function NaverIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="#ffffff"
        d="M16.27 12.85 7.38 0H0v24h7.73V11.15L16.62 24H24V0h-7.73v12.85z"
      />
    </svg>
  );
}
