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
        <button
          className={`${style.menuButton} ${style.menuButtonActive}`}
          type="button"
        >
          홈
        </button>

        <button className={style.menuButton} type="button">
          프로젝트
        </button>

        <button className={style.menuButton} type="button">
          마이페이지
        </button>
      </nav>
    </div>
  );
}