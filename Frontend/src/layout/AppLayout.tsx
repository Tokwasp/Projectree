import { useState, type ReactNode } from "react";
import { Outlet } from "react-router-dom";
import AppHeader from "../components/AppHeader/AppHeader";
import Sidebar from "../components/Sidebar/Sidebar";
import style from "./AppLayout.module.css";

interface AppLayoutProps {
  sidebar?: ReactNode;
}

export default function AppLayout({ sidebar }: AppLayoutProps) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const canCollapseSidebar = sidebar === undefined;

  return (
    <div className={style.layout}>
      <aside
        className={`${style.sidebar} ${canCollapseSidebar && isSidebarCollapsed ? style.sidebarCollapsed : ""}`}
      >
        {sidebar ?? (
          <Sidebar
            isCollapsed={isSidebarCollapsed}
            onToggle={() => setIsSidebarCollapsed((current) => !current)}
          />
        )}
      </aside>

      <div
        className={`${style.mainArea} ${canCollapseSidebar && isSidebarCollapsed ? style.mainAreaExpanded : ""}`}
      >
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
