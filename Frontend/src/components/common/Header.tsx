import style from "../../css/components/common/Header.module.css";
import Logo from "../../assets/logo.svg";

export default function Header() {
  return (
    <header className={style.header}>
      <div className={style.logoContainer}>
        <img src={Logo} alt="Logo" className={style.logo} />
        <span>Projectree</span>
      </div>
      <button className={style.loginBtn}>로그인</button>
    </header>
  );
}
