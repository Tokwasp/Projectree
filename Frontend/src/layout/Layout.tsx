import { Outlet } from "react-router-dom";

export default function Layout() {
  return (
    <div style={{ height: "100%" }}>
      <Outlet />
    </div>
  );
}
