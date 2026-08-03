import { Link, NavLink } from "react-router-dom";
import Logo from "../../assets/logo.svg";
import style from "./Sidebar.module.css";

export default function Sidebar() {
  return (
    <div className={style.container}>
      <Link
        className={style.brand}
        to="/home"
        aria-label="서비스 홈으로 이동"
      >
        <img className={style.logo} src={Logo} alt="" />
        <span>Projectree</span>
      </Link>

      <nav className={style.navigation} aria-label="주요 메뉴">
        <NavLink
          className={({ isActive }) =>
            `${style.menuButton} ${isActive ? style.menuButtonActive : ""}`
          }
          to="/home"
        >
          홈
        </NavLink>

        <NavLink
          className={({ isActive }) =>
            `${style.menuButton} ${isActive ? style.menuButtonActive : ""}`
          }
          to="/projects"
        >
          프로젝트
        </NavLink>

        <NavLink
          className={({ isActive }) =>
            `${style.menuButton} ${isActive ? style.menuButtonActive : ""}`
          }
          to="/mypage"
        >
          마이페이지
        </NavLink>
      </nav>
    </div>
  );
}
