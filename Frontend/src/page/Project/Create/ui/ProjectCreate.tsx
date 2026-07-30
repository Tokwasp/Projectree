import { useNavigate } from "react-router-dom";
import ProjectCreateForm from "../components/ProjectCreateForm/ProjectCreateForm";

export default function ProjectCreate() {
  const navigate = useNavigate();

  return (
    <ProjectCreateForm
      onCancel={() => navigate(-1)}
      onCreate={() => undefined}
    />
  );
}