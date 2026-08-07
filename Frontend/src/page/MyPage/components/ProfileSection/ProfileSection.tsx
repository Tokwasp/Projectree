import style from "./ProfileSection.module.css";

interface ProfileSectionProps {
  name: string;
  email: string;
  profileImageUrl: string | null;
}

export default function ProfileSection({
  name,
  email,
  profileImageUrl,
}: ProfileSectionProps) {
  return (
    <section className={style.section}>
      <div className={style.profile}>
        {profileImageUrl ? (
          <img
            className={style.profileImage}
            src={profileImageUrl}
            alt={`${name} 프로필`}
          />
        ) : (
          <div className={style.profileFallback} aria-hidden="true">
            {name.charAt(0)}
          </div>
        )}

        <div className={style.profileInfo}>
          <h2 className={style.name}>{name}</h2>
          <p className={style.profileDescription}>{email}</p>
        </div>
      </div>
    </section>
  );
}
