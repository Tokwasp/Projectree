import { useNavigate } from "react-router-dom";
import ProjectCreateForm, {
  type ProjectCreateFormData,
} from "../components/project/ProjectCreateForm";
import useCategories from "../hooks/useCategories";
import useCreateProject from "../hooks/useCreateProject";

export default function ProjectCreatePage() {
  const navigate = useNavigate();
  const {
    createProject,
    isCreating,
    error: createError,
  } = useCreateProject();
  const {
    categories,
    error: categoriesError,
  } = useCategories();

  const handleCreate = async (formData: ProjectCreateFormData) => {
    if (isCreating) {
      return;
    }

    const projectId = await createProject({
      title: formData.title,
      content: formData.description,
      photoUrl: formData.imageUrl || null,
      categoryIds: formData.categoryIds,
    });

    if (projectId === null) {
      return;
    }

    navigate(`/projects/${projectId}`);
  };

  return (
    <ProjectCreateForm
      onCancel={() => navigate(-1)}
      onCreate={handleCreate}
      isCreating={isCreating}
      categories={categories}
      categoriesError={categoriesError}
      createError={createError}
    />
  );
}
