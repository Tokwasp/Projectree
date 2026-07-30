import { Outlet } from "react-router-dom";
import Header from "../components/Header/Header";
import LoginModal from "../components/LoginModal/LoginModal";

export default function Layout() {
  return (
    <>
      <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
        <Header />
        <Outlet />
      </div>
      <LoginModal />
    </>
  );
}
