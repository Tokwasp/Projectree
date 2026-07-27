import { NavLink } from "react-router-dom";
import Logo from "../../assets/logo.svg";
import style from "../../css/components/common/Sidebar.module.css";

export default function Sidebar() {
  return (
    <div className={style.container}>
      <div className={style.brand}>
        <img className={style.logo} src={Logo} alt="" />
        <span>Projectree</span>
      </div>

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

        <button className={style.menuButton} type="button">
          마이페이지
        </button>
      </nav>
    </div>
  );
}
