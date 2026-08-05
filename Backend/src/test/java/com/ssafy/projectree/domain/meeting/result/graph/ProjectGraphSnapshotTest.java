package com.ssafy.projectree.domain.meeting.result.graph;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotParser;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotValidator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProjectGraphSnapshotTest extends IntegrationTestSupport {

    @Autowired
    private ProjectGraphSnapshotParser parser;
    @Autowired
    private ProjectGraphSnapshotValidator validator;
    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void parsesStrictUtf8AndCanonicalizesSnapshotIds() throws Exception {
        Fixture fixture = fixture();
        ProjectGraphSnapshot parsed = parser.parse(objectMapper.writeValueAsBytes(fixture.snapshot()));
        ProjectGraphSnapshot normalized = validator.validate(fixture.event(), fixture.payload(), parsed);

        assertThat(normalized.commandId()).isEqualTo(fixture.commandId());
        assertThat(normalized.nodes()).extracting(ProjectGraphSnapshotNode::nodeId)
                .contains(fixture.decisionId(), fixture.actionId());
        assertThatThrownBy(() -> parser.parse(new byte[]{(byte) 0xC3, (byte) 0x28}))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    @Test
    void rejectsInvalidMergedTargetAndDuplicateEvidenceOrder() {
        Fixture fixture = fixture();
        ProjectGraphSnapshotNode invalidMerged = new ProjectGraphSnapshotNode(
                UUID.randomUUID().toString(), null, null, fixture.actionId(), GraphNodeType.DECISION,
                GraphNodeCategory.BACKEND, GraphNodeState.MERGED, "old", "content", null, 1,
                Instant.now(), Instant.now()
        );
        ProjectGraphSnapshot invalidMerge = replaceNodes(fixture.snapshot(),
                List.of(fixture.snapshot().nodes().getFirst(), invalidMerged));
        assertThatThrownBy(() -> validator.validate(fixture.event(), fixture.payload(), invalidMerge))
                .isInstanceOf(AnalysisResultContractException.class);

        ProjectGraphSnapshotEvidence duplicateOrder = new ProjectGraphSnapshotEvidence(
                UUID.randomUUID().toString(), fixture.actionId(), 2, "quote", null, 0L, 1L, 1
        );
        ProjectGraphSnapshot invalidEvidence = new ProjectGraphSnapshot(
                fixture.snapshot().snapshotSchemaVersion(), fixture.snapshot().projectId(), fixture.snapshot().meetingId(),
                fixture.snapshot().commandId(), fixture.snapshot().graphVersion(), fixture.snapshot().generatedAt(),
                fixture.snapshot().nodes(), List.of(fixture.snapshot().evidences().getFirst(), duplicateOrder), List.of()
        );
        assertThatThrownBy(() -> validator.validate(fixture.event(), fixture.payload(), invalidEvidence))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    private ProjectGraphSnapshot replaceNodes(ProjectGraphSnapshot snapshot, List<ProjectGraphSnapshotNode> nodes) {
        return new ProjectGraphSnapshot(
                snapshot.snapshotSchemaVersion(), snapshot.projectId(), snapshot.meetingId(), snapshot.commandId(),
                snapshot.graphVersion(), snapshot.generatedAt(), nodes, snapshot.evidences(), snapshot.mergeRecords()
        );
    }

    private Fixture fixture() {
        String commandId = UUID.randomUUID().toString();
        String decisionId = UUID.randomUUID().toString();
        String actionId = UUID.randomUUID().toString();
        Instant now = Instant.parse("2026-08-04T12:00:00Z");
        ProjectGraphSnapshot snapshot = new ProjectGraphSnapshot(
                1, 1, 2, commandId.toUpperCase(), 3, now,
                List.of(
                        new ProjectGraphSnapshotNode(decisionId.toUpperCase(), null, null, null,
                                GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE,
                                "decision", "content", null, 1, now, now),
                        new ProjectGraphSnapshotNode(actionId.toUpperCase(), 2, decisionId.toUpperCase(), null,
                                GraphNodeType.ACTION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE,
                                "action", "content", null, 1, now, now)
                ),
                List.of(new ProjectGraphSnapshotEvidence(UUID.randomUUID().toString().toUpperCase(), actionId.toUpperCase(),
                        2, "quote", "speaker", 0L, 100L, 1)),
                List.of(objectMapper.createObjectNode().put("ignored", true))
        );
        AnalysisResultEventEnvelope event = new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                now, 1, 2, commandId, objectMapper.createObjectNode()
        );
        ProjectGraphChangedPayload payload = new ProjectGraphChangedPayload(
                GraphResultSourceType.MEETING_ANALYSIS, 3,
                new GraphSnapshotReference("projectree-graph", "graphs/file.json", "application/json", 1024, "a".repeat(64))
        );
        return new Fixture(commandId, decisionId, actionId, event, payload, snapshot);
    }

    private record Fixture(
            String commandId,
            String decisionId,
            String actionId,
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            ProjectGraphSnapshot snapshot
    ) {
    }
}
