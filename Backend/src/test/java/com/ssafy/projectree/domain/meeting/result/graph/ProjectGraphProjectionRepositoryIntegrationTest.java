package com.ssafy.projectree.domain.meeting.result.graph;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class ProjectGraphProjectionRepositoryIntegrationTest extends IntegrationTestSupport {

    @Autowired
    private ProjectGraphSyncRepository graphSyncRepository;
    @Autowired
    private ProjectNodeProjectionRepository nodeRepository;
    @Autowired
    private NodeEvidenceProjectionRepository evidenceRepository;

    @Test
    void providesTheMinimalRepositoriesNeededForFutureProjectionReplacement() {
        int projectId = 901;
        String nodeId = UUID.randomUUID().toString();
        graphSyncRepository.saveAndFlush(ProjectGraphSync.initial(projectId, Instant.now()));
        nodeRepository.saveAndFlush(ProjectNodeProjection.from(projectId, node(nodeId), Instant.now()));
        evidenceRepository.saveAndFlush(NodeEvidenceProjection.from(evidence(nodeId), Instant.now()));

        assertThat(graphSyncRepository.findByProjectIdForUpdate(projectId)).isPresent();
        assertThat(nodeRepository.findAllByProjectId(projectId)).hasSize(1);
        assertThat(nodeRepository.countByProjectId(projectId)).isEqualTo(1);
        assertThat(nodeRepository.findByNodeIdAndProjectId(nodeId, projectId)).isPresent();
        assertThat(evidenceRepository.findAllByNodeId(nodeId)).hasSize(1);
        assertThat(evidenceRepository.countByNodeId(nodeId)).isEqualTo(1);

        evidenceRepository.deleteAllByNodeId(nodeId);
        nodeRepository.deleteAllByProjectId(projectId);
        assertThat(nodeRepository.countByProjectId(projectId)).isZero();
    }

    private ProjectGraphSnapshotNode node(String nodeId) {
        Instant now = Instant.now();
        return new ProjectGraphSnapshotNode(
                nodeId, 1, null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND,
                GraphNodeState.ACTIVE, "title", "content", null, 1, now, now
        );
    }

    private ProjectGraphSnapshotEvidence evidence(String nodeId) {
        return new ProjectGraphSnapshotEvidence(
                UUID.randomUUID().toString(), nodeId, 1, "quote", null, null, null, 1
        );
    }
}
