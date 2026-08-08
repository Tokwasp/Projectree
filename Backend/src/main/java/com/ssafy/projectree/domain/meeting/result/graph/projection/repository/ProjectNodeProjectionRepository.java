package com.ssafy.projectree.domain.meeting.result.graph.projection.repository;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;

public interface ProjectNodeProjectionRepository extends JpaRepository<ProjectNodeProjection, String> {

    List<ProjectNodeProjection> findAllByProjectId(int projectId);

    boolean existsByProjectId(int projectId);

    long countByProjectId(int projectId);

    @Modifying(flushAutomatically = true)
    @Query("delete from ProjectNodeProjection node where node.projectId = :projectId")
    void deleteAllByProjectId(@Param("projectId") int projectId);

    Optional<ProjectNodeProjection> findByNodeIdAndProjectId(String nodeId, int projectId);

    List<ProjectNodeProjection> findAllByProjectIdAndGraphState(
            int projectId,
            GraphNodeState graphState
    );

    Page<ProjectNodeProjection> findAllByProjectIdAndGraphState(
            int projectId,
            GraphNodeState graphState,
            Pageable pageable
    );

    List<ProjectNodeProjection> findAllByProjectIdAndGraphStateAndMergedIntoNodeId(
            int projectId,
            GraphNodeState graphState,
            String mergedIntoNodeId
    );

    Page<ProjectNodeProjection> findAllByProjectIdAndSourceMeetingId(
            int projectId,
            int sourceMeetingId,
            Pageable pageable
    );

    List<ProjectNodeProjection> findAllByProjectIdAndSourceMeetingId(
            int projectId,
            int sourceMeetingId
    );
}
