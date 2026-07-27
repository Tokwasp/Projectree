import { Link, NavLink, useParams } from "react-router-dom";
import Logo from "../../assets/logo.svg";
import style from "../../css/components/common/Sidebar.module.css";

export default function ProjectSidebar() {
  const { projectId } = useParams<{ projectId: string }>();
  const projectHomePath = `/projects/${projectId}`;

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

      <nav className={style.navigation} aria-label="프로젝트 메뉴">
        <NavLink
          className={({ isActive }) =>
            `${style.menuButton} ${
              isActive ? style.menuButtonActive : ""
            }`
          }
          to={projectHomePath}
          end
        >
          프로젝트 홈
        </NavLink>

        <button className={style.menuButton} type="button">
          회의
        </button>

        <button className={style.menuButton} type="button">
          노드
        </button>

        <button className={style.menuButton} type="button">
          팀원
        </button>

        <button className={style.menuButton} type="button">
          설정
        </button>
      </nav>
    </div>
  );
}
