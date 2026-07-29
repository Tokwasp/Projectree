package com.ssafy.projectree.domain.project.repository;

import com.ssafy.projectree.domain.project.entity.Project;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProjectRepository extends JpaRepository<Project, Integer> {
}
