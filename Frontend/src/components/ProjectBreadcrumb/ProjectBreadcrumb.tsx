import { Link } from "react-router-dom";
import Logo from "../../assets/logo.svg";
import style from "./ProjectBreadcrumb.module.css";

interface ProjectBreadcrumbProps {
  currentProjectName: string;
}

export default function ProjectBreadcrumb({
  currentProjectName,
}: ProjectBreadcrumbProps) {

  return (
    <nav className={style.container} aria-label="현재 위치">
      <Link className={style.brand} to="/home" aria-label="서비스 홈으로 이동">
        <img className={style.logo} src={Logo} alt="" />
      </Link>
      <Link
        className={style.path}
        to="/home"
      >
        홈
      </Link>
      <span className={style.divider} aria-hidden="true">
        /
      </span>
      <Link
        className={style.path}
        to="/projects"
      >
        프로젝트
      </Link>
      <span className={style.divider} aria-hidden="true">
        /
      </span>
      <span className={style.pathCurrent} aria-current="page">
        {currentProjectName}
      </span>
    </nav>
  );
}
