import style from "./ProjectManagementSkeleton.module.css";

export default function ProjectManagementSkeleton() {
  return (
    <div
      className={style.page}
      role="status"
      aria-label="프로젝트 설정을 불러오는 중"
      aria-busy="true"
    >
      <div className={style.pageHeader}>
        <h1 className={style.pageTitle}>프로젝트 설정</h1>
        <p className={style.pageDescription}>
          프로젝트 정보와 참여 상태를 관리할 수 있습니다.
        </p>
      </div>

      <div className={style.contentGrid}>
        <section className={style.mainCard}>
          <div className={style.cardHeader}>
            <span className={`${style.skeleton} ${style.cardTitle}`} />
            <span className={`${style.skeleton} ${style.cardDescription}`} />
          </div>

          <div className={style.settingRow}>
            <div className={style.settingText}>
              <span className={`${style.skeleton} ${style.settingLabel}`} />
              <span
                className={`${style.skeleton} ${style.settingDescription}`}
              />
            </div>
            <div className={style.photoControl}>
              <span className={`${style.skeleton} ${style.photo}`} />
              <span className={`${style.skeleton} ${style.button}`} />
            </div>
          </div>

          {Array.from({ length: 2 }).map((_, index) => (
            <div className={style.settingRow} key={index}>
              <div className={style.settingText}>
                <span className={`${style.skeleton} ${style.settingLabel}`} />
                <span
                  className={`${style.skeleton} ${style.settingDescription}`}
                />
              </div>
              <div className={style.valueControl}>
                <span className={`${style.skeleton} ${style.value}`} />
                <span className={`${style.skeleton} ${style.button}`} />
              </div>
            </div>
          ))}
        </section>

        <div className={style.sideColumn}>
          <section className={style.infoCard}>
            <div className={style.cardHeader}>
              <span className={`${style.skeleton} ${style.cardTitle}`} />
            </div>

            <div className={style.infoList}>
              {Array.from({ length: 3 }).map((_, index) => (
                <div className={style.infoRow} key={index}>
                  <span className={`${style.skeleton} ${style.infoLabel}`} />
                  <span className={`${style.skeleton} ${style.infoValue}`} />
                </div>
              ))}
            </div>
          </section>

          <section className={style.actionCard}>
            <div className={style.cardHeader}>
              <span className={`${style.skeleton} ${style.cardTitle}`} />
              <span
                className={`${style.skeleton} ${style.actionDescription}`}
              />
            </div>
            <span className={`${style.skeleton} ${style.actionButton}`} />
          </section>
        </div>
      </div>

      <span className={style.screenReaderText}>
        프로젝트 설정을 불러오는 중입니다.
      </span>
    </div>
  );
}
