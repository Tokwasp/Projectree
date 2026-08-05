import { Link } from "react-router-dom";
import CreateProjectIcon from "../../assets/create_project_icon.png";
import InvitationIcon from "../../assets/invitation_icon.png";
import QuickActionIcon from "../../assets/quick_action_icon.png";
import RecentProjectIcon from "../../assets/recent_project_icon.png";
import style from "./QuickActions.module.css";

interface QuickActionsProps {
  recentProjectId?: number;
}

export default function QuickActions({
  recentProjectId,
}: QuickActionsProps) {
  const hasRecentProject = recentProjectId !== undefined;

  return (
    <section className={style.section} aria-labelledby="quick-actions-title">
      <h2 className={style.title} id="quick-actions-title">
        <span className={style.titleIcon} aria-hidden="true">
          <img src={QuickActionIcon} alt="" />
        </span>
        빠른 작업
      </h2>

      <div className={style.actionGrid}>
        <Link className={style.actionCard} to="/projects/create">
          <span className={style.iconBox} aria-hidden="true">
            <img className={style.actionIcon} src={CreateProjectIcon} alt="" />
          </span>
          <span className={style.actionCopy}>
            <strong>새 프로젝트 만들기</strong>
            <small>새로운 프로젝트를 시작해보세요.</small>
          </span>
          <span className={style.arrow} aria-hidden="true">
            ›
          </span>
        </Link>

        <Link
          className={style.actionCard}
          to={hasRecentProject ? `/projects/${recentProjectId}` : "/"}
        >
          <span className={style.iconBox} aria-hidden="true">
            <img className={style.actionIcon} src={RecentProjectIcon} alt="" />
          </span>
          <span className={style.actionCopy}>
            <strong>
              {hasRecentProject
                ? "최근 프로젝트 이어가기"
                : "Projectree 설명 보기"}
            </strong>
            <small>
              {hasRecentProject
                ? "최근 작업을 이어서 진행해보세요."
                : "Projectree의 서비스를 확인하세요."}
            </small>
          </span>
          <span className={style.arrow} aria-hidden="true">
            ›
          </span>
        </Link>

        <button className={style.actionCard} type="button">
          <span className={style.iconBox} aria-hidden="true">
            <img className={style.actionIcon} src={InvitationIcon} alt="" />
          </span>
          <span className={style.actionCopy}>
            <strong>초대 확인</strong>
            <small>프로젝트 초대를 확인하세요.</small>
          </span>
          <span className={style.arrow} aria-hidden="true">
            ›
          </span>
        </button>
      </div>
    </section>
  );
}
