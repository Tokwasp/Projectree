import { useState, type ReactNode } from "react";
import { Outlet } from "react-router-dom";
import AppHeader from "../components/AppHeader/AppHeader";
import Sidebar from "../components/Sidebar/Sidebar";
import style from "./AppLayout.module.css";

interface AppLayoutProps {
  sidebar?: ReactNode;
  headerStart?: ReactNode;
}

export default function AppLayout({ sidebar, headerStart }: AppLayoutProps) {
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const canCollapseSidebar = sidebar === undefined;
  const hasProjectSidebar = sidebar !== undefined;

  return (
    <div className={style.layout}>
      <aside
        className={`${style.sidebar} ${canCollapseSidebar && isSidebarCollapsed ? style.sidebarCollapsed : ""} ${hasProjectSidebar ? style.projectSidebar : ""}`}
      >
        {sidebar ?? (
          <Sidebar
            isCollapsed={isSidebarCollapsed}
            onToggle={() => setIsSidebarCollapsed((current) => !current)}
          />
        )}
      </aside>

      <div
        className={`${style.mainArea} ${canCollapseSidebar && isSidebarCollapsed ? style.mainAreaExpanded : ""} ${hasProjectSidebar ? style.projectMainArea : ""}`}
      >
        <header
          className={`${style.header} ${isScrolled ? style.headerScrolled : ""}`}
        >
          <AppHeader startContent={headerStart} />
        </header>

        <div
          className={style.contentArea}
          onScroll={(event) => setIsScrolled(event.currentTarget.scrollTop > 0)}
        >
          <main className={style.content}>
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
