import ProjectSidebar from "../components/ProjectSidebar/ProjectSidebar";
import AppLayout from "./AppLayout";

export default function ProjectLayout() {
  return <AppLayout sidebar={<ProjectSidebar />} />;
}