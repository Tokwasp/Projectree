import style from "./Footer.module.css";

export default function Footer() {
  return (
    <footer className={style.footer}>
      <div className={style.inner}>
        <small className={style.copyright}>
          © 2026 Projectree. All rights reserved.
        </small>
      </div>
    </footer>
  );
}