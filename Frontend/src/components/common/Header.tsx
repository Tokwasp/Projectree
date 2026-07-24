import style from "../../css/components/common/Header.module.css";
import Logo from "../../assets/logo.svg";
import { useLoginModal } from "../../contexts/LoginModalContext";

export default function Header() {
  const { openLoginModal } = useLoginModal();

  return (
    <header className={style.header}>
      <div className={style.logoContainer}>
        <img src={Logo} alt="Logo" className={style.logo} />
        <span>Projectree</span>
      </div>
      <button className={style.loginBtn} onClick={openLoginModal}>
        로그인
      </button>
    </header>
  );
}
