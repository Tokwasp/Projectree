package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus;
import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteRejectedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteRejectionReason;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
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
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Transactional(propagation = Propagation.NOT_SUPPORTED)
class NodeDeleteRejectedEventHandlerIntegrationTest extends IntegrationTestSupport {

    private static final Instant NOW = Instant.parse("2026-08-07T02:00:00Z");

    @Autowired private NodeDeleteRejectedEventHandler handler;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private ProjectGraphSyncRepository syncRepository;
    @Autowired private ProjectNodeProjectionRepository nodeRepository;
    @Autowired private NodeDeleteCommandRepository commandRepository;
    @Autowired private NodeDeleteCommandItemRepository itemRepository;
    @Autowired private MeetingAnalysisResultInboxRepository inboxRepository;
    @Autowired private ObjectMapper objectMapper;

    @AfterEach
    void cleanUp() {
        inboxRepository.deleteAll();
        itemRepository.deleteAll();
        commandRepository.deleteAll();
        nodeRepository.deleteAll();
        syncRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void rejectionMarksCommandRejectedReleasesGuardAndKeepsProjection() {
        Fixture fixture = fixture(false);
        AnalysisResultEventEnvelope event = rejectedEvent(
                fixture,
                NodeDeleteRejectionReason.GRAPH_VERSION_CONFLICT
        );

        handler.handle(event);

        NodeDeleteCommand command = commandRepository
                .findByCommandId(fixture.commandId())
                .orElseThrow();
        assertThat(command.getStatus()).isEqualTo(NodeDeleteCommandStatus.REJECTED);
        assertThat(command.getReasonCode()).isEqualTo("GRAPH_VERSION_CONFLICT");
        assertThat(command.getResultEventId()).isEqualTo(event.eventId());
        assertThat(command.getResultGraphVersion()).isNull();
        assertThat(command.getCompletedAt()).isNotNull();
        assertThat(syncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isFalse();
        assertThat(nodeRepository.countByProjectId(fixture.projectId())).isEqualTo(1);
        assertThat(inboxRepository.count()).isEqualTo(1);
    }

    @Test
    void guardOwnershipMismatchRollsBackRejectionAndInbox() {
        Fixture fixture = fixture(true);
        AnalysisResultEventEnvelope event = rejectedEvent(
                fixture,
                NodeDeleteRejectionReason.NODE_NOT_FOUND
        );

        assertThatThrownBy(() -> handler.handle(event))
                .isInstanceOf(AnalysisResultContractException.class)
                .hasMessageContaining("active graph operation");

        NodeDeleteCommand command = commandRepository
                .findByCommandId(fixture.commandId())
                .orElseThrow();
        ProjectGraphSync sync = syncRepository.findById(fixture.projectId())
                .orElseThrow();
        assertThat(command.getStatus()).isEqualTo(NodeDeleteCommandStatus.PENDING);
        assertThat(command.getReasonCode()).isNull();
        assertThat(sync.getActiveCommandId()).isEqualTo(fixture.guardCommandId());
        assertThat(inboxRepository.count()).isZero();
    }

    private Fixture fixture(boolean mismatchedGuard) {
        Project project = Project.builder().title("project").content("content").build();
        project.addMember(ProjectMember.createMember(15, ProjectRole.OWNER));
        project = projectRepository.saveAndFlush(project);
        String nodeId = UUID.randomUUID().toString();
        nodeRepository.saveAndFlush(ProjectNodeProjection.from(
                project.getId(),
                new ProjectGraphSnapshotNode(
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
                        3,
                        NOW,
                        NOW
                ),
                NOW
        ));
        UUID commandId = UUID.randomUUID();
        NodeDeleteCommand command = commandRepository.saveAndFlush(
                NodeDeleteCommand.pending(
                        commandId,
                        project.getId(),
                        12,
                        15,
                        1,
                        0,
                        LocalDateTime.of(2026, 8, 7, 11, 0)
                )
        );
        itemRepository.saveAndFlush(NodeDeleteCommandItem.requested(
                command,
                nodeId,
                3,
                LocalDateTime.of(2026, 8, 7, 11, 0)
        ));
        String guardCommandId = mismatchedGuard
                ? UUID.randomUUID().toString()
                : commandId.toString();
        ProjectGraphSync sync = ProjectGraphSync.initial(project.getId(), NOW);
        sync.advanceTo(12, UUID.randomUUID().toString(), NOW.plusSeconds(1));
        sync.acquireGraphOperation(
                guardCommandId,
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                NOW.plusSeconds(2)
        );
        syncRepository.saveAndFlush(sync);
        return new Fixture(
                project.getId(),
                commandId.toString(),
                guardCommandId
        );
    }

    private AnalysisResultEventEnvelope rejectedEvent(
            Fixture fixture,
            NodeDeleteRejectionReason reason
    ) {
        return new AnalysisResultEventEnvelope(
                3,
                UUID.randomUUID().toString(),
                AnalysisResultEventType.NODE_DELETE_REJECTED,
                NOW.plusSeconds(3),
                fixture.projectId(),
                null,
                fixture.commandId(),
                objectMapper.valueToTree(new NodeDeleteRejectedPayload(
                        GraphResultSourceType.NODE_DELETE,
                        reason
                ))
        );
    }

    private record Fixture(
            int projectId,
            String commandId,
            String guardCommandId
    ) {
    }
}
