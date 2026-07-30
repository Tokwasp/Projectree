import { Link, NavLink, useParams } from "react-router-dom";
import Logo from "../../assets/logo.svg";
import MemberIcon from "../../assets/icons/sidebar/member.png";
import MeetingIcon from "../../assets/icons/sidebar/meeting.png";
import NodeIcon from "../../assets/icons/sidebar/node.png";
import ProjectHomeIcon from "../../assets/icons/sidebar/project-home.png";
import SettingsIcon from "../../assets/icons/sidebar/settings.png";
import style from "../Sidebar/Sidebar.module.css";

export default function ProjectSidebar() {
  const { projectId } = useParams<{ projectId: string }>();
  const projectHomePath = `/projects/${projectId}`;
  const projectMembersPath = `/projects/${projectId}/members`;

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
          <img
            className={style.menuIcon}
            src={ProjectHomeIcon}
            alt=""
            aria-hidden="true"
          />
          <span>프로젝트 홈</span>
        </NavLink>

        <button className={style.menuButton} type="button">
          <img
            className={style.menuIcon}
            src={MeetingIcon}
            alt=""
            aria-hidden="true"
          />
          <span>회의</span>
        </button>

        <button className={style.menuButton} type="button">
          <img
            className={style.menuIcon}
            src={NodeIcon}
            alt=""
            aria-hidden="true"
          />
          <span>노드</span>
        </button>

        <NavLink
          className={({ isActive }) =>
            `${style.menuButton} ${
              isActive ? style.menuButtonActive : ""
            }`
          }
          to={projectMembersPath}
        >
          <img
            className={style.menuIcon}
            src={MemberIcon}
            alt=""
            aria-hidden="true"
          />
          <span>팀원</span>
        </NavLink>

        <button className={style.menuButton} type="button">
          <img
            className={style.menuIcon}
            src={SettingsIcon}
            alt=""
            aria-hidden="true"
          />
          <span>설정</span>
        </button>
      </nav>
    </div>
  );
}
