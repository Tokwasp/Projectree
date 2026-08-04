package com.ssafy.projectree.domain.meeting.result.graph.projection.repository;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.Optional;

public interface ProjectNodeProjectionRepository extends JpaRepository<ProjectNodeProjection, String> {

    List<ProjectNodeProjection> findAllByProjectId(int projectId);

    long countByProjectId(int projectId);

    void deleteAllByProjectId(int projectId);

    Optional<ProjectNodeProjection> findByNodeIdAndProjectId(String nodeId, int projectId);
}
