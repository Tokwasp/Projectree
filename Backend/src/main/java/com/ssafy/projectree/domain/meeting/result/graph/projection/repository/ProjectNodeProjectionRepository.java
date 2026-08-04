package com.ssafy.projectree.domain.meeting.result.graph.projection.repository;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface ProjectNodeProjectionRepository extends JpaRepository<ProjectNodeProjection, String> {

    List<ProjectNodeProjection> findAllByProjectId(int projectId);

    long countByProjectId(int projectId);

    @Modifying(flushAutomatically = true)
    @Query("delete from ProjectNodeProjection node where node.projectId = :projectId")
    void deleteAllByProjectId(@Param("projectId") int projectId);

    Optional<ProjectNodeProjection> findByNodeIdAndProjectId(String nodeId, int projectId);
}
