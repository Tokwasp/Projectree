import style from "./Header.module.css";
import Logo from "../../assets/logo.svg";
import { useLoginModalStore } from "../../store/loginModalStore";

export default function Header() {
  const { openLoginModal } = useLoginModalStore();

  return (
    <header className={style.header}>
      <div className={style.headerInner}>
        <div className={style.logoContainer}>
          <img src={Logo} alt="Logo" className={style.logo} />
          <span>Projectree</span>
        </div>
        <button className={style.loginBtn} onClick={openLoginModal}>
          로그인
        </button>
      </div>
    </header>
  );
}
