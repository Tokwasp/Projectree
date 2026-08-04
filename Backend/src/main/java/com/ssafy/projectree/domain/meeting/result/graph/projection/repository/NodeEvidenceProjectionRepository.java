package com.ssafy.projectree.domain.meeting.result.graph.projection.repository;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface NodeEvidenceProjectionRepository extends JpaRepository<NodeEvidenceProjection, String> {

    List<NodeEvidenceProjection> findAllByNodeId(String nodeId);

    long countByNodeId(String nodeId);

    void deleteAllByNodeId(String nodeId);
}
