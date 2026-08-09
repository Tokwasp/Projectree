import { useParams } from "react-router-dom";
import ProjectBreadcrumb from "../components/ProjectBreadcrumb/ProjectBreadcrumb";
import ProjectSidebar from "../components/ProjectSidebar/ProjectSidebar";
import { mockProjectHome } from "../mocks/ProjectHomeMocks";
import useProjectList from "../page/Project/List/hooks/useProjectList";
import AppLayout from "./AppLayout";

export default function ProjectLayout() {
  const { projectId } = useParams<{ projectId: string }>();
  const parsedProjectId = Number(projectId);
  const currentProjectId = Number.isInteger(parsedProjectId)
    ? parsedProjectId
    : null;
  const { projects, isLoading } = useProjectList(0, 100);
  const currentProject = projects.find(
    (project) => project.projectId === currentProjectId,
  );
  const currentProjectName = isLoading
    ? "프로젝트 불러오는 중..."
    : (currentProject?.title ?? mockProjectHome.title);

  return (
    <AppLayout
      headerStart={
        <ProjectBreadcrumb currentProjectName={currentProjectName} />
      }
      sidebar={
        <ProjectSidebar
          projects={projects}
          currentProjectId={currentProjectId}
          currentProjectName={currentProjectName}
        />
      }
    />
  );
}
