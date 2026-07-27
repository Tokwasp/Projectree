import { createContext, useContext, useState, type ReactNode } from "react";

interface LoginModalContextValue {
  isOpen: boolean;
  openLoginModal: () => void;
  closeLoginModal: () => void;
}

const LoginModalContext = createContext<LoginModalContextValue | null>(null);

export function LoginModalProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);

  const openLoginModal = () => setIsOpen(true);
  const closeLoginModal = () => setIsOpen(false);

  return (
    <LoginModalContext.Provider
      value={{ isOpen, openLoginModal, closeLoginModal }}
    >
      {children}
    </LoginModalContext.Provider>
  );
}

export function useLoginModal() {
  const ctx = useContext(LoginModalContext);
  if (!ctx) {
    throw new Error("useLoginModal must be used within a LoginModalProvider");
  }
  return ctx;
}
