package com.ssafy.projectree.domain.meeting.result.graph.projection.repository;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface NodeEvidenceProjectionRepository extends JpaRepository<NodeEvidenceProjection, String> {

    List<NodeEvidenceProjection> findAllByNodeId(String nodeId);

    long countByNodeId(String nodeId);

    void deleteAllByNodeId(String nodeId);

    @Modifying(flushAutomatically = true)
    @Query("""
            delete from NodeEvidenceProjection evidence
            where evidence.nodeId in (
                select node.nodeId
                from ProjectNodeProjection node
                where node.projectId = :projectId
            )
            """)
    void deleteAllByProjectId(@Param("projectId") int projectId);
}
