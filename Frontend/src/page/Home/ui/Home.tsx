import RecentProjectSection from "../components/RecentProjectSection/RecentProjectSection";
import { mockProjects } from "../../../mocks/ProjectMocks";
import { useEffect } from "react";

export default function Home() {
  const fetchProjects = async () => {
    try {
      const response = await fetch(
        `${import.meta.env.VITE_BASE_URL}/projects`,
        {
          method: "GET",
          headers: {
            "Content-Type": "application/json",
          },
        },
      );
    } catch (error) {
      console.error("Error fetching projects:", error);
    }
  };
  useEffect(() => {
    fetchProjects();
  }, []);

  return <RecentProjectSection projects={mockProjects.slice(0, 8)} />;
}
