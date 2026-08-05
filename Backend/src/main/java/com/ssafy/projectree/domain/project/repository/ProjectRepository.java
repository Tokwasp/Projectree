package com.ssafy.projectree.domain.project.repository;

import com.ssafy.projectree.domain.project.dto.response.ProjectItemResponse;
import com.ssafy.projectree.domain.project.entity.Project;
import jakarta.persistence.LockModeType;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface ProjectRepository extends JpaRepository<Project, Integer> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from Project p where p.id = :projectId")
    Optional<Project> findByIdForUpdate(@Param("projectId") int projectId);

    @Query(value = """
            select new com.ssafy.projectree.domain.project.dto.response.ProjectItemResponse(
                       p.id, p.title, p.photoUrl,
                       (select count(pm2.id) from ProjectMember pm2 where pm2.project = p))
            from Project p
            join p.projectMembers pm
            where pm.memberId = :memberId
    """,
            countQuery = """
            select count(p)
            from Project p
            join p.projectMembers pm
            where pm.memberId = :memberId
    """)
    Page<ProjectItemResponse> findProjectItemsByMemberId(@Param("memberId") int memberId, Pageable pageable);
}
