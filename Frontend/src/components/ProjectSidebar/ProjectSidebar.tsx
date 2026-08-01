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

  const menus = [
    {
      label: "프로젝트 홈",
      icon: ProjectHomeIcon,
      to: `/projects/${projectId}`,
      end: true,
    },
    {
      label: "회의",
      icon: MeetingIcon,
      to: `/projects/${projectId}/meeting`,
    },
    {
      label: "노드",
      icon: NodeIcon,
      to: `/projects/${projectId}/tree`,
    },
    {
      label: "팀원",
      icon: MemberIcon,
      to: `/projects/${projectId}/members`,
    },
    {
      label: "설정",
      icon: SettingsIcon,
      onClick: () => {
        // TODO: 설정 페이지 이동 또는 기능 추가
      },
    },
  ];

  return (
    <div className={style.container}>
      <Link className={style.brand} to="/home" aria-label="서비스 홈으로 이동">
        <img className={style.logo} src={Logo} alt="" />
        <span>Projectree</span>
      </Link>

      <nav className={style.navigation} aria-label="프로젝트 메뉴">
        {menus.map((menu) =>
          menu.to ? (
            <NavLink
              key={menu.label}
              to={menu.to}
              end={menu.end}
              className={({ isActive }) =>
                `${style.menuButton} ${isActive ? style.menuButtonActive : ""}`
              }
            >
              <img
                className={style.menuIcon}
                src={menu.icon}
                alt=""
                aria-hidden="true"
              />
              <span>{menu.label}</span>
            </NavLink>
          ) : (
            <button
              key={menu.label}
              className={style.menuButton}
              type="button"
              onClick={menu.onClick}
            >
              <img
                className={style.menuIcon}
                src={menu.icon}
                alt=""
                aria-hidden="true"
              />
              <span>{menu.label}</span>
            </button>
          ),
        )}
      </nav>
    </div>
  );
}
