import { useNavigate } from "react-router-dom";
import ProjectCreateForm from "../components/project/ProjectCreateForm";

export default function ProjectCreatePage() {
  const navigate = useNavigate();

  return (
    <ProjectCreateForm
      onCancel={() => navigate(-1)}
      onCreate={() => undefined}
    />
  );
}