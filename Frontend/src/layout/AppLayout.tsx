import type { ReactNode } from "react";
import { Outlet } from "react-router-dom";
import AppHeader from "../components/AppHeader/AppHeader";
import Sidebar from "../components/Sidebar/Sidebar";
import style from "./AppLayout.module.css";

interface AppLayoutProps {
  sidebar?: ReactNode;
}

export default function AppLayout({ sidebar }: AppLayoutProps) {
  return (
    <div className={style.layout}>
      <aside className={style.sidebar}>
        {sidebar ?? <Sidebar />}
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