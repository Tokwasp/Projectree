import RecentProjectSection from "../components/RecentProjectSection/RecentProjectSection";
import { mockProjects } from "../../../mocks/ProjectMocks";

export default function Home() {
  return <RecentProjectSection projects={mockProjects.slice(0, 8)} />;
}
