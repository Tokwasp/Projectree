import ProjectSidebar from "../components/project/ProjectSidebar";
import AppLayout from "./AppLayout";

export default function ProjectLayout() {
  return <AppLayout sidebar={<ProjectSidebar />} />;
}