import { Link, NavLink } from "react-router-dom";
import HomeIcon from "../../assets/icons/sidebar/home.png";
import MyPageIcon from "../../assets/icons/sidebar/mypage.png";
import ProjectIcon from "../../assets/icons/sidebar/project.png";
import Logo from "../../assets/logo.svg";
import style from "./Sidebar.module.css";

const menus = [
  { label: "Home", icon: HomeIcon, to: "/home" },
  { label: "Project", icon: ProjectIcon, to: "/projects" },
  { label: "Mypage", icon: MyPageIcon, to: "/mypage" },
];

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

export default function Sidebar({ isCollapsed, onToggle }: SidebarProps) {
  return (
    <div
      className={`${style.container} ${style.mainSidebar} ${isCollapsed ? style.mainSidebarCollapsed : ""}`}
    >
      <Link
        className={style.brand}
        to="/home"
        aria-label="서비스 홈으로 이동"
      >
        <img className={style.logo} src={Logo} alt="" />
      </Link>

      <button
        className={style.collapseButton}
        type="button"
        onClick={onToggle}
        aria-label={isCollapsed ? "사이드바 펼치기" : "사이드바 접기"}
        aria-expanded={!isCollapsed}
      >
        <span aria-hidden="true">{isCollapsed ? "›" : "‹"}</span>
      </button>

      <nav className={style.navigation} aria-label="주요 메뉴">
        {menus.map((menu) => (
          <NavLink
            className={({ isActive }) =>
              `${style.menuButton} ${isActive ? style.menuButtonActive : ""}`
            }
            key={menu.label}
            to={menu.to}
            aria-label={menu.label}
          >
            <img
              className={style.menuIcon}
              src={menu.icon}
              alt=""
              aria-hidden="true"
            />
            <span className={style.menuLabel}>{menu.label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
