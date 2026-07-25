import { useState } from "react";
import ProjectListSection from "../components/project/ProjectListSection";
import { mockProjects } from "../mocks/ProjectMocks";

export default function ProjectPage() {
  const [searchKeyword, setSearchKeyword] = useState("");

  const normalizedKeyword = searchKeyword.trim().toLowerCase();

  const filteredProjects = mockProjects.filter((project) =>
    project.title.toLowerCase().includes(normalizedKeyword),
  );

  return (
    <ProjectListSection
      projects={filteredProjects}
      searchKeyword={searchKeyword}
      onSearchChange={setSearchKeyword}
    />
  );
}