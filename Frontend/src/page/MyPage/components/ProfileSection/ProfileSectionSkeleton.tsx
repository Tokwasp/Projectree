import style from "./ProfileSectionSkeleton.module.css";

export default function ProfileSectionSkeleton() {
  return (
    <section
      className={style.section}
      role="status"
      aria-label="회원 정보를 불러오는 중입니다."
    >
      <div className={style.profile} aria-hidden="true">
        <div className={style.profileImage} />

        <div className={style.profileInfo}>
          <div className={style.name} />
          <div className={style.email} />
        </div>
      </div>
    </section>
  );
}