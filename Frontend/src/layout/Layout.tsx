import { Outlet } from "react-router-dom";
import Header from "../components/common/Header";

export default function Layout() {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <Header />
      <Outlet />
    </div>
  );
}
