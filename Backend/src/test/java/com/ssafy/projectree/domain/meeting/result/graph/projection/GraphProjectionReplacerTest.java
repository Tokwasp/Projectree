package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class GraphProjectionReplacerTest {

    @Mock private NodeEvidenceProjectionRepository evidenceRepository;
    @Mock private ProjectNodeProjectionRepository nodeRepository;

    @Test
    void replacesProjectProjectionInForeignKeySafeOrder() {
        GraphProjectionReplacer replacer = new GraphProjectionReplacer(evidenceRepository, nodeRepository);
        int projectId = 12;
        Instant syncedAt = Instant.parse("2026-08-05T00:00:00Z");
        String nodeId = UUID.randomUUID().toString();
        ProjectGraphSnapshot snapshot = new ProjectGraphSnapshot(
                1, projectId, 33, UUID.randomUUID().toString(), 1, syncedAt,
                List.of(new ProjectGraphSnapshotNode(nodeId, 33, null, null,
                        GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE,
                        "title", "content", null, 1, syncedAt, syncedAt)),
                List.of(new ProjectGraphSnapshotEvidence(UUID.randomUUID().toString(), nodeId, 33,
                        "quote", null, null, null, 1)),
                List.of()
        );

        replacer.replace(projectId, snapshot, syncedAt);

        InOrder inOrder = inOrder(evidenceRepository, nodeRepository);
        inOrder.verify(evidenceRepository).deleteAllByProjectId(projectId);
        inOrder.verify(nodeRepository).deleteAllByProjectId(projectId);
        inOrder.verify(nodeRepository).saveAllAndFlush(org.mockito.ArgumentMatchers.any());
        inOrder.verify(evidenceRepository).saveAllAndFlush(org.mockito.ArgumentMatchers.any());

        verify(nodeRepository).saveAllAndFlush(argThat(nodes -> {
            assertThat(nodes).hasSize(1);
            return true;
        }));
    }
}
