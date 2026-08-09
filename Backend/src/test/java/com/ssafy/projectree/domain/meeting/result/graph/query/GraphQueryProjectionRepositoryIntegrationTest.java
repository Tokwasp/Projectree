package com.ssafy.projectree.domain.meeting.result.graph.query;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphLinkSource;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class GraphQueryProjectionRepositoryIntegrationTest extends IntegrationTestSupport {

    @Autowired private ProjectNodeProjectionRepository nodeRepository;
    @Autowired private NodeEvidenceProjectionRepository evidenceRepository;

    @Test
    void supportsProjectScopedStateNodeMergedTargetAndMeetingQueries() {
        ProjectNodeProjection active = saveNode(1, 10, "10000000-0000-0000-0000-000000000000",
                GraphNodeState.ACTIVE, null, 1);
        ProjectNodeProjection merged = saveNode(1, 10, "20000000-0000-0000-0000-000000000000",
                GraphNodeState.MERGED, active.getNodeId(), 2);
        ProjectNodeProjection unattached = saveNode(1, 11, "30000000-0000-0000-0000-000000000000",
                GraphNodeState.UNATTACHED, null, 3);
        saveNode(2, 10, "40000000-0000-0000-0000-000000000000",
                GraphNodeState.ACTIVE, null, 4);

        assertThat(nodeRepository.findAllByProjectIdAndGraphState(1, GraphNodeState.ACTIVE))
                .extracting(ProjectNodeProjection::getNodeId).containsExactly(active.getNodeId());
        assertThat(nodeRepository.findByNodeIdAndProjectId(active.getNodeId(), 2)).isEmpty();
        assertThat(nodeRepository.findAllByProjectIdAndGraphStateAndMergedIntoNodeId(
                1, GraphNodeState.MERGED, active.getNodeId()
        )).extracting(ProjectNodeProjection::getNodeId).containsExactly(merged.getNodeId());
        assertThat(nodeRepository.findAllByProjectIdAndSourceMeetingId(
                1, 10, PageRequest.of(0, 20, Sort.by("sourceCreatedAt"))
        ).getContent()).extracting(ProjectNodeProjection::getNodeId)
                .containsExactly(active.getNodeId(), merged.getNodeId());
        assertThat(nodeRepository.findAllByProjectIdAndGraphState(
                1, GraphNodeState.UNATTACHED, PageRequest.of(0, 1)
        ).getContent()).extracting(ProjectNodeProjection::getNodeId)
                .containsExactly(unattached.getNodeId());
    }

    @Test
    void supportsSingleNodeEvidenceSortAndBatchEvidenceLookup() {
        ProjectNodeProjection first = saveNode(1, 10, "10000000-0000-0000-0000-000000000000",
                GraphNodeState.ACTIVE, null, 1);
        ProjectNodeProjection second = saveNode(1, 10, "20000000-0000-0000-0000-000000000000",
                GraphNodeState.MERGED, first.getNodeId(), 2);
        saveEvidence("40000000-0000-0000-0000-000000000000", first.getNodeId(), 2);
        saveEvidence("30000000-0000-0000-0000-000000000000", first.getNodeId(), 1);
        saveEvidence("50000000-0000-0000-0000-000000000000", second.getNodeId(), 1);

        assertThat(evidenceRepository.findAllByNodeIdOrderByEvidenceOrderAscEvidenceIdAsc(first.getNodeId()))
                .extracting(NodeEvidenceProjection::getEvidenceId)
                .containsExactly(
                        "30000000-0000-0000-0000-000000000000",
                        "40000000-0000-0000-0000-000000000000"
                );
        assertThat(evidenceRepository.findAllByNodeIdIn(List.of(first.getNodeId(), second.getNodeId())))
                .hasSize(3)
                .extracting(NodeEvidenceProjection::getNodeId)
                .containsOnly(first.getNodeId(), second.getNodeId());
    }

    private ProjectNodeProjection saveNode(
            int projectId,
            int meetingId,
            String nodeId,
            GraphNodeState state,
            String mergedIntoNodeId,
            long second
    ) {
        Instant time = Instant.parse("2026-08-05T00:00:0" + second + "Z");
        return nodeRepository.saveAndFlush(ProjectNodeProjection.from(projectId, new ProjectGraphSnapshotNode(
                nodeId, meetingId, null, mergedIntoNodeId, GraphNodeType.DECISION,
                GraphNodeCategory.BACKEND, state, "title", "content", GraphLinkSource.LLM_GENERATED,
                1, time, time
        ), time));
    }

    private void saveEvidence(String evidenceId, String nodeId, int order) {
        evidenceRepository.saveAndFlush(NodeEvidenceProjection.from(new ProjectGraphSnapshotEvidence(
                evidenceId, nodeId, 10, "quote", null, null, null, order
        ), Instant.parse("2026-08-05T00:00:10Z")));
    }
}
