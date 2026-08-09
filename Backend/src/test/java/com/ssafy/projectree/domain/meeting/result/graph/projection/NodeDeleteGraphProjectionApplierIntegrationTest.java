package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeDeleteCommandPayload;
import com.ssafy.projectree.domain.meeting.command.NodeDeleteRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NodeDeleteGraphProjectionApplierIntegrationTest extends IntegrationTestSupport {

    private static final Instant NOW = Instant.parse("2026-08-07T03:00:00Z");

    @Autowired private NodeDeleteGraphProjectionApplier applier;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private ProjectGraphSyncRepository syncRepository;
    @Autowired private ProjectNodeProjectionRepository nodeRepository;
    @Autowired private NodeEvidenceProjectionRepository evidenceRepository;
    @Autowired private NodeDeleteCommandRepository commandRepository;
    @Autowired private NodeDeleteCommandItemRepository itemRepository;
    @Autowired private MeetingAnalysisCommandOutboxRepository outboxRepository;
    @Autowired private MeetingAnalysisResultInboxRepository inboxRepository;
    @Autowired private ObjectMapper objectMapper;

    @AfterEach
    void cleanUp() {
        inboxRepository.deleteAll();
        evidenceRepository.deleteAll();
        itemRepository.deleteAll();
        commandRepository.deleteAll();
        outboxRepository.deleteAll();
        nodeRepository.deleteAll();
        syncRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void validDeleteSnapshotAtomicallyReplacesProjectionAndCompletesCommand() {
        Fixture fixture = fixture(null);
        ProjectGraphChangedPayload payload = payload(13);
        AnalysisResultEventEnvelope event = event(fixture, payload);

        GraphProjectionApplyResult result = applier.apply(
                event,
                payload,
                snapshot(
                        fixture,
                        13,
                        List.of(snapshotNode(fixture.visibleNodeId(), 7))
                )
        );

        assertThat(result.projectionUpdated()).isTrue();
        assertThat(result.currentGraphVersion()).isEqualTo(13);
        assertThat(nodeRepository.findAllByProjectId(fixture.projectId()))
                .extracting(ProjectNodeProjection::getNodeId)
                .containsExactly(fixture.visibleNodeId())
                .doesNotContain(
                        fixture.requestedNodeId(),
                        fixture.mergedSourceNodeId()
                );
        NodeDeleteCommand command = commandRepository
                .findByCommandId(fixture.commandId())
                .orElseThrow();
        assertThat(command.getStatus()).isEqualTo(NodeDeleteCommandStatus.SUCCEEDED);
        assertThat(command.getResultEventId()).isEqualTo(event.eventId());
        assertThat(command.getResultGraphVersion()).isEqualTo(13);
        ProjectGraphSync sync = syncRepository.findById(fixture.projectId())
                .orElseThrow();
        assertThat(sync.getCurrentGraphVersion()).isEqualTo(13);
        assertThat(sync.getLastCommandId()).isEqualTo(fixture.commandId());
        assertThat(sync.hasActiveCommand()).isFalse();
        assertThat(inboxRepository.count()).isEqualTo(1);
    }

    @Test
    void snapshotContainingDeletedNodeIsRejectedWithoutStateChange() {
        Fixture fixture = fixture(null);
        ProjectGraphChangedPayload payload = payload(13);

        assertThatThrownBy(() -> applier.apply(
                event(fixture, payload),
                payload,
                snapshot(
                        fixture,
                        13,
                        List.of(
                                snapshotNode(fixture.requestedNodeId(), 5),
                                snapshotNode(fixture.visibleNodeId(), 7)
                        )
                )
        ))
                .isInstanceOf(AnalysisResultContractException.class)
                .hasMessageContaining("still contains");

        assertPendingStateUnchanged(fixture);
    }

    @Test
    void nonSequentialGraphVersionIsRejectedWithoutStateChange() {
        Fixture fixture = fixture(null);
        ProjectGraphChangedPayload payload = payload(12);

        assertThatThrownBy(() -> applier.apply(
                event(fixture, payload),
                payload,
                snapshot(
                        fixture,
                        12,
                        List.of(snapshotNode(fixture.visibleNodeId(), 7))
                )
        ))
                .isInstanceOf(AnalysisResultContractException.class)
                .hasMessageContaining("graphVersion");

        assertPendingStateUnchanged(fixture);
    }

    @Test
    void payloadRequestedIdsMustMatchStoredRequestedItems() {
        Fixture fixture = fixture(UUID.randomUUID().toString());
        ProjectGraphChangedPayload payload = payload(13);

        assertThatThrownBy(() -> applier.apply(
                event(fixture, payload),
                payload,
                snapshot(
                        fixture,
                        13,
                        List.of(snapshotNode(fixture.visibleNodeId(), 7))
                )
        ))
                .isInstanceOf(AnalysisResultContractException.class)
                .hasMessageContaining("requested node IDs");

        assertPendingStateUnchanged(fixture);
    }

    private Fixture fixture(String payloadRequestedNodeId) {
        Project project = Project.builder().title("project").content("content").build();
        project.addMember(ProjectMember.createMember(15, ProjectRole.OWNER));
        project = projectRepository.saveAndFlush(project);
        String requestedNodeId = UUID.randomUUID().toString();
        String mergedSourceNodeId = UUID.randomUUID().toString();
        String visibleNodeId = UUID.randomUUID().toString();
        nodeRepository.saveAllAndFlush(List.of(
                projection(
                        project.getId(),
                        requestedNodeId,
                        null,
                        GraphNodeState.ACTIVE,
                        5
                ),
                projection(
                        project.getId(),
                        mergedSourceNodeId,
                        requestedNodeId,
                        GraphNodeState.MERGED,
                        3
                ),
                projection(
                        project.getId(),
                        visibleNodeId,
                        null,
                        GraphNodeState.ACTIVE,
                        7
                )
        ));

        UUID commandId = UUID.randomUUID();
        LocalDateTime requestedAt = LocalDateTime.of(2026, 8, 7, 12, 0);
        NodeDeleteCommand deleteCommand = commandRepository.saveAndFlush(
                NodeDeleteCommand.pending(
                        commandId,
                        project.getId(),
                        12,
                        15,
                        1,
                        1,
                        requestedAt
                )
        );
        itemRepository.saveAllAndFlush(List.of(
                NodeDeleteCommandItem.requested(
                        deleteCommand,
                        requestedNodeId,
                        5,
                        requestedAt
                ),
                NodeDeleteCommandItem.mergedSource(
                        deleteCommand,
                        mergedSourceNodeId,
                        3,
                        requestedAt
                )
        ));
        String requestedIdInPayload = payloadRequestedNodeId == null
                ? requestedNodeId
                : payloadRequestedNodeId;
        NodeDeleteRequestedCommand requestedCommand =
                new NodeDeleteRequestedCommand(
                        NodeDeleteRequestedCommand.CURRENT_SCHEMA_VERSION,
                        commandId,
                        MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                        NOW,
                        project.getId(),
                        new NodeDeleteCommandPayload(
                                List.of(requestedIdInPayload),
                                12,
                                15
                        )
                );
        MeetingAnalysisCommandOutbox outbox = outboxRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pendingNodeDelete(
                        commandId,
                        project.getId(),
                        objectMapper.writeValueAsString(requestedCommand),
                        15,
                        requestedAt
                )
        );
        deleteCommand.attachOutbox(outbox.getId());
        commandRepository.saveAndFlush(deleteCommand);

        ProjectGraphSync sync = ProjectGraphSync.initial(project.getId(), NOW);
        sync.advanceTo(12, UUID.randomUUID().toString(), NOW.plusSeconds(1));
        sync.acquireGraphOperation(
                commandId.toString(),
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                NOW.plusSeconds(2)
        );
        syncRepository.saveAndFlush(sync);
        return new Fixture(
                project.getId(),
                commandId.toString(),
                requestedNodeId,
                mergedSourceNodeId,
                visibleNodeId
        );
    }

    private ProjectNodeProjection projection(
            int projectId,
            String nodeId,
            String mergedIntoNodeId,
            GraphNodeState state,
            long nodeVersion
    ) {
        return ProjectNodeProjection.from(
                projectId,
                new ProjectGraphSnapshotNode(
                        nodeId,
                        null,
                        null,
                        mergedIntoNodeId,
                        GraphNodeType.DECISION,
                        GraphNodeCategory.BACKEND,
                        state,
                        "title",
                        "content",
                        null,
                        nodeVersion,
                        NOW,
                        NOW
                ),
                NOW
        );
    }

    private ProjectGraphChangedPayload payload(long graphVersion) {
        return new ProjectGraphChangedPayload(
                GraphResultSourceType.NODE_DELETE,
                graphVersion,
                new GraphSnapshotReference(
                        "graph-bucket",
                        "graph-snapshots/delete.json",
                        "application/json",
                        1,
                        "a".repeat(64)
                )
        );
    }

    private AnalysisResultEventEnvelope event(
            Fixture fixture,
            ProjectGraphChangedPayload payload
    ) {
        return new AnalysisResultEventEnvelope(
                3,
                UUID.randomUUID().toString(),
                AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                NOW.plusSeconds(3),
                fixture.projectId(),
                null,
                fixture.commandId(),
                objectMapper.valueToTree(payload)
        );
    }

    private ProjectGraphSnapshot snapshot(
            Fixture fixture,
            long graphVersion,
            List<ProjectGraphSnapshotNode> nodes
    ) {
        return new ProjectGraphSnapshot(
                1,
                fixture.projectId(),
                null,
                fixture.commandId(),
                graphVersion,
                NOW.plusSeconds(3),
                nodes,
                List.of(),
                List.of()
        );
    }

    private ProjectGraphSnapshotNode snapshotNode(String nodeId, long nodeVersion) {
        return new ProjectGraphSnapshotNode(
                nodeId,
                null,
                null,
                null,
                GraphNodeType.DECISION,
                GraphNodeCategory.BACKEND,
                GraphNodeState.ACTIVE,
                "title",
                "content",
                null,
                nodeVersion,
                NOW,
                NOW
        );
    }

    private void assertPendingStateUnchanged(Fixture fixture) {
        assertThat(nodeRepository.countByProjectId(fixture.projectId())).isEqualTo(3);
        assertThat(commandRepository.findByCommandId(fixture.commandId())
                .orElseThrow().getStatus()).isEqualTo(NodeDeleteCommandStatus.PENDING);
        ProjectGraphSync sync = syncRepository.findById(fixture.projectId())
                .orElseThrow();
        assertThat(sync.getCurrentGraphVersion()).isEqualTo(12);
        assertThat(sync.getActiveCommandId()).isEqualTo(fixture.commandId());
        assertThat(inboxRepository.count()).isZero();
    }

    private record Fixture(
            int projectId,
            String commandId,
            String requestedNodeId,
            String mergedSourceNodeId,
            String visibleNodeId
    ) {
    }
}
