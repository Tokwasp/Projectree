import type { UserProfile } from "../../types/User";
import style from "../../css/mypage/ProfileSection.module.css";

interface ProfileSectionProps {
  user: UserProfile;
}

export default function ProfileSection({ user }: ProfileSectionProps) {
  return (
    <section className={style.section}>
      <div className={style.profile}>
        {user.profileImageUrl ? (
          <img
            className={style.profileImage}
            src={user.profileImageUrl}
            alt={`${user.name} 프로필`}
          />
        ) : (
          <div className={style.profileFallback} aria-hidden="true">
            {user.name.charAt(0)}
          </div>
        )}

        <div className={style.profileInfo}>
          <h1 className={style.name}>{user.name}</h1>
          <p className={style.email}>{user.email}</p>
        </div>
      </div>

      <button className={style.editButton} type="button">
        수정
      </button>
    </section>
  );
}
