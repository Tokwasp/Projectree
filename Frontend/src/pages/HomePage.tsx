import RecentProjectSection from "../components/home/RecentProjectSection";
import { mockProjects } from "../mocks/ProjectMocks";

export default function HomePage() {
  return <RecentProjectSection projects={mockProjects.slice(0, 8)} />;
}
