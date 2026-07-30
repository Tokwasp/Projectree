package com.ssafy.projectree.domain.project.repository;

import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProjectMemberRepository extends JpaRepository<ProjectMember, Integer> {

    boolean existsByProjectIdAndMemberId(int projectId, int memberId);

    boolean existsByProjectIdAndMemberIdAndRole(int projectId, int memberId, ProjectRole role);
}
