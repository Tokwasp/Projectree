import { Outlet } from "react-router-dom";
import Header from "../components/common/Header";
import LoginModal from "../components/auth/LoginModal";
import { LoginModalProvider } from "../contexts/LoginModalContext";

export default function Layout() {
  return (
    <LoginModalProvider>
      <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
        <Header />
        <Outlet />
      </div>
      <LoginModal />
    </LoginModalProvider>
  );
}
