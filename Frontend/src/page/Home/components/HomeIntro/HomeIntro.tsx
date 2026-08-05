import style from "./HomeIntro.module.css";

interface HomeIntroProps {
  name: string;
  projectCount: number;
}

export default function HomeIntro({ name, projectCount }: HomeIntroProps) {
  return (
    <section className={style.intro} aria-labelledby="home-greeting">
      <h1 className={style.title} id="home-greeting">
        안녕하세요, <span className={style.userName}>{name}</span> 님!
      </h1>
      <p className={style.description}>
        {projectCount > 0 ? (
          <>
            현재 <strong className={style.projectCount}>{projectCount}</strong>개의
            프로젝트에 참여하고 있어요. 지난 회의의 흐름을 이어가세요.
          </>
        ) : (
          "현재 참여 중인 프로젝트가 없어요. 새 프로젝트를 만들거나 초대를 확인해보세요."
        )}
      </p>
    </section>
  );
}
