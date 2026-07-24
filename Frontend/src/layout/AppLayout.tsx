import { Outlet } from "react-router-dom";
import AppHeader from "../components/common/AppHeader";
import Sidebar from "../components/common/Sidebar";
import style from "../css/layout/AppLayout.module.css";

export default function AppLayout() {
  return (
    <div className={style.layout}>
      <aside className={style.sidebar}>
        <Sidebar />
      </aside>

      <div className={style.mainArea}>
        <header className={style.header}>
          <AppHeader />
        </header>

        <main className={style.content}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}