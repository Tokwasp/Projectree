import { useAuthStore } from "../../../store/authStore";
import HomeIntro from "../components/HomeIntro/HomeIntro";
import QuickActions from "../components/QuickActions/QuickActions";
import RecentProjectSection from "../components/RecentProjectSection/RecentProjectSection";
import useProjectList from "../../Project/List/hooks/useProjectList";
import style from "../css/Home.module.css";

const PROJECT_LIST_SIZE = 8;
const RECENT_PROJECT_COUNT = 4;

export default function Home() {
  const name = useAuthStore((state) => state.name);
  const { projects, totalElements, isLoading, error } = useProjectList(
    0,
    PROJECT_LIST_SIZE,
  );

  return (
    <div className={style.home}>
      <HomeIntro
        name={name ?? "Projectree"}
        projectCount={totalElements}
        isLoading={isLoading}
        hasError={error !== null}
      />
      <QuickActions recentProjectId={projects[0]?.projectId} />
      {error ? (
        <p role="alert">{error}</p>
      ) : (
        <RecentProjectSection
          projects={projects.slice(0, RECENT_PROJECT_COUNT)}
          isLoading={isLoading}
        />
      )}
    </div>
  );
}
