package com.ssafy.projectree.domain.project.repository;

import com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface ProjectMemberRepository extends JpaRepository<ProjectMember, Integer> {

    @Query("""
            select new com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse(
                       m.id, m.name, m.email, pm.role, pm.createdAt)
            from ProjectMember pm
            join Member m on m.id = pm.memberId
            where pm.project.id = :projectId
            order by case when pm.role = com.ssafy.projectree.domain.project.entity.ProjectRole.OWNER
                          then 0
                          else 1
                     end,
                     pm.id
            """)
    List<ProjectMemberResponse> findMemberResponsesByProjectId(@Param("projectId") int projectId);
}
