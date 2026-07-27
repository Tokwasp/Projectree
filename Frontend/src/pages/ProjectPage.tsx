import { useState } from "react";
import ProjectListSection from "../components/project/ProjectListSection";
import { mockProjects } from "../mocks/ProjectMocks";

const PROJECTS_PER_PAGE = 8;

export default function ProjectPage() {
  const [searchKeyword, setSearchKeyword] = useState("");
  const [currentPage, setCurrentPage] = useState(1);

  const normalizedKeyword = searchKeyword.trim().toLowerCase();

  const filteredProjects = mockProjects.filter((project) =>
    project.title.toLowerCase().includes(normalizedKeyword),
  );

  const totalPages = Math.ceil(filteredProjects.length / PROJECTS_PER_PAGE);
  const startIndex = (currentPage - 1) * PROJECTS_PER_PAGE;
  const paginatedProjects = filteredProjects.slice(
    startIndex,
    startIndex + PROJECTS_PER_PAGE,
  );

  const handleSearchChange = (value: string) => {
    setSearchKeyword(value);
    setCurrentPage(1);
  };

  return (
    <ProjectListSection
      projects={paginatedProjects}
      searchKeyword={searchKeyword}
      currentPage={currentPage}
      totalPages={totalPages}
      onSearchChange={handleSearchChange}
      onPageChange={setCurrentPage}
    />
  );
}