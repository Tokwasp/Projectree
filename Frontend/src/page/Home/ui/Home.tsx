import RecentProjectSection from "../components/RecentProjectSection/RecentProjectSection";
import useProjectList from "../../Project/List/hooks/useProjectList";

const PROJECT_LIST_SIZE = 8;
const RECENT_PROJECT_COUNT = 4;

export default function Home() {
  const { projects, isLoading, error } = useProjectList(0, PROJECT_LIST_SIZE);

  if (isLoading) {
    return <p>최근 프로젝트를 불러오는 중입니다.</p>;
  }

  if (error) {
    return <p role="alert">{error}</p>;
  }

  return (
    <RecentProjectSection projects={projects.slice(0, RECENT_PROJECT_COUNT)} />
  );
}
