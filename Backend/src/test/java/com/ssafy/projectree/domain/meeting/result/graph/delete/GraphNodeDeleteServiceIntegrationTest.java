package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeDeleteRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteRequest;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationErrorCode;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.function.Function;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Transactional(propagation = Propagation.NOT_SUPPORTED)
class GraphNodeDeleteServiceIntegrationTest extends IntegrationTestSupport {

    private static final int MEMBER_ID = 15;
    private static final long GRAPH_VERSION = 12L;
    private static final Instant NODE_TIME = Instant.parse("2026-08-07T01:00:00Z");

    @Autowired
    private GraphNodeDeleteService service;
    @Autowired
    private ProjectRepository projectRepository;
    @Autowired
    private ProjectGraphSyncRepository syncRepository;
    @Autowired
    private ProjectNodeProjectionRepository nodeRepository;
    @Autowired
    private NodeDeleteCommandRepository commandRepository;
    @Autowired
    private NodeDeleteCommandItemRepository itemRepository;
    @Autowired
    private MeetingAnalysisCommandOutboxRepository outboxRepository;
    @Autowired
    private ObjectMapper objectMapper;

    @AfterEach
    void cleanUp() {
        itemRepository.deleteAll();
        commandRepository.deleteAll();
        outboxRepository.deleteAll();
        nodeRepository.deleteAll();
        syncRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void stagesPendingDeleteWithTransitiveMergedSourcesAndRequestedOnlyPayload() {
        Fixture fixture = fixture();
        String target = node(fixture.projectId(), GraphNodeState.ACTIVE, null, null, 31);
        String child = node(fixture.projectId(), GraphNodeState.ACTIVE, target, null, 32);
        String directSource = node(
                fixture.projectId(),
                GraphNodeState.MERGED,
                null,
                target,
                21
        );
        String transitiveSource = node(
                fixture.projectId(),
                GraphNodeState.MERGED,
                null,
                directSource,
                11
        );

        var response = service.deleteNodes(
                fixture.projectId(),
                MEMBER_ID,
                new GraphNodeDeleteRequest(List.of(target, child), GRAPH_VERSION)
        );

        assertThat(response.projectId()).isEqualTo(fixture.projectId());
        assertThat(response.nodeIds()).containsExactly(target, child);
        assertThat(response.expectedGraphVersion()).isEqualTo(GRAPH_VERSION);
        assertThat(response.status()).isEqualTo(NodeDeleteCommandStatus.PENDING);

        ProjectGraphSync sync = syncRepository.findById(fixture.projectId()).orElseThrow();
        assertThat(sync.getActiveCommandId()).isEqualTo(response.commandId().toString());
        assertThat(sync.getActiveCommandType())
                .isEqualTo(MeetingAnalysisCommandType.NODE_DELETE_REQUESTED);

        NodeDeleteCommand deleteCommand = commandRepository
                .findByCommandId(response.commandId().toString())
                .orElseThrow();
        assertThat(deleteCommand.getStatus()).isEqualTo(NodeDeleteCommandStatus.PENDING);
        assertThat(deleteCommand.getRequestedNodeCount()).isEqualTo(2);
        assertThat(deleteCommand.getMergedSourceCount()).isEqualTo(2);
        assertThat(deleteCommand.getTotalNodeCount()).isEqualTo(4);

        List<NodeDeleteCommandItem> items =
                itemRepository.findAllByCommandId(deleteCommand.getCommandId());
        Map<String, NodeDeleteCommandItem> itemsByNodeId = items.stream()
                .collect(Collectors.toMap(
                        NodeDeleteCommandItem::getNodeId,
                        Function.identity()
                ));
        assertThat(itemsByNodeId.get(target).getItemType())
                .isEqualTo(NodeDeleteItemType.REQUESTED);
        assertThat(itemsByNodeId.get(target).getExpectedNodeVersion()).isEqualTo(31);
        assertThat(itemsByNodeId.get(child).getItemType())
                .isEqualTo(NodeDeleteItemType.REQUESTED);
        assertThat(itemsByNodeId.get(child).getExpectedNodeVersion()).isEqualTo(32);
        assertThat(itemsByNodeId.get(directSource).getItemType())
                .isEqualTo(NodeDeleteItemType.MERGED_SOURCE);
        assertThat(itemsByNodeId.get(directSource).getExpectedNodeVersion()).isEqualTo(21);
        assertThat(itemsByNodeId.get(transitiveSource).getItemType())
                .isEqualTo(NodeDeleteItemType.MERGED_SOURCE);
        assertThat(itemsByNodeId.get(transitiveSource).getExpectedNodeVersion()).isEqualTo(11);

        MeetingAnalysisCommandOutbox outbox = outboxRepository.findAll().getFirst();
        assertThat(outbox.getCommandType())
                .isEqualTo(MeetingAnalysisCommandType.NODE_DELETE_REQUESTED);
        assertThat(outbox.getMeeting()).isNull();
        assertThat(outbox.getTargetProjectId()).isEqualTo(fixture.projectId());
        assertThat(outbox.getTargetNodeId()).isNull();
        assertThat(deleteCommand.getOutboxId()).isEqualTo(outbox.getId());
        NodeDeleteRequestedCommand sqsCommand = objectMapper.readValue(
                outbox.getPayload(),
                NodeDeleteRequestedCommand.class
        );
        assertThat(sqsCommand.payload().nodeIds()).containsExactly(target, child);
        assertThat(sqsCommand.payload().nodeIds())
                .doesNotContain(directSource, transitiveSource);
        assertThat(sqsCommand.payload().expectedGraphVersion()).isEqualTo(GRAPH_VERSION);
        assertThat(sqsCommand.payload().requestedByMemberId()).isEqualTo(MEMBER_ID);
    }

    @Test
    void graphVersionConflictRollsBackGuardAndCreatesNothing() {
        Fixture fixture = fixture();
        String nodeId = node(fixture.projectId(), GraphNodeState.ACTIVE, null, null, 1);

        assertDeleteError(
                fixture.projectId(),
                new GraphNodeDeleteRequest(List.of(nodeId), GRAPH_VERSION - 1),
                GraphNodeDeleteErrorCode.GRAPH_VERSION_CONFLICT
        );

        assertThat(syncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isFalse();
        assertDeleteStorageEmpty();
    }

    @Test
    void missingActiveDescendantRollsBackEntireRequest() {
        Fixture fixture = fixture();
        String parent = node(fixture.projectId(), GraphNodeState.ACTIVE, null, null, 1);
        node(fixture.projectId(), GraphNodeState.ACTIVE, parent, null, 2);

        assertDeleteError(
                fixture.projectId(),
                new GraphNodeDeleteRequest(List.of(parent), GRAPH_VERSION),
                GraphNodeDeleteErrorCode.NODE_DELETE_SET_INCOMPLETE
        );

        assertThat(syncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isFalse();
        assertDeleteStorageEmpty();
    }

    @Test
    void existingGraphOperationRejectsDeleteWithoutChangingStorage() {
        Fixture fixture = fixture();
        String nodeId = node(fixture.projectId(), GraphNodeState.ACTIVE, null, null, 1);
        ProjectGraphSync sync = syncRepository.findById(fixture.projectId()).orElseThrow();
        String activeCommandId = UUID.randomUUID().toString();
        sync.acquireGraphOperation(
                activeCommandId,
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                NODE_TIME
        );
        syncRepository.saveAndFlush(sync);

        assertDeleteError(
                fixture.projectId(),
                new GraphNodeDeleteRequest(List.of(nodeId), GRAPH_VERSION),
                ProjectGraphOperationErrorCode.GRAPH_OPERATION_IN_PROGRESS
        );

        assertThat(syncRepository.findById(fixture.projectId()).orElseThrow()
                .getActiveCommandId()).isEqualTo(activeCommandId);
        assertDeleteStorageEmpty();
    }

    @Test
    void duplicateNodeIdIsRejectedBeforeGuardAcquisition() {
        Fixture fixture = fixture();
        String nodeId = node(fixture.projectId(), GraphNodeState.ACTIVE, null, null, 1);

        assertDeleteError(
                fixture.projectId(),
                new GraphNodeDeleteRequest(List.of(nodeId, nodeId), GRAPH_VERSION),
                GraphNodeDeleteErrorCode.NODE_DELETE_DUPLICATE_NODE_ID
        );

        assertThat(syncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isFalse();
        assertDeleteStorageEmpty();
    }

    @Test
    void nodeOutsideProjectIsReportedAsNotFoundAndRollsBackGuard() {
        Fixture fixture = fixture();
        Fixture other = fixture();
        String otherNode = node(other.projectId(), GraphNodeState.ACTIVE, null, null, 1);

        assertDeleteError(
                fixture.projectId(),
                new GraphNodeDeleteRequest(List.of(otherNode), GRAPH_VERSION),
                com.ssafy.projectree.domain.meeting.result.graph.query.GraphQueryErrorCode.NODE_NOT_FOUND
        );

        assertThat(syncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isFalse();
        assertDeleteStorageEmpty();
    }

    private Fixture fixture() {
        Project project = Project.builder().title("project").content("content").build();
        project.addMember(ProjectMember.createMember(MEMBER_ID, ProjectRole.MEMBER));
        project = projectRepository.saveAndFlush(project);
        ProjectGraphSync sync = ProjectGraphSync.initial(project.getId(), NODE_TIME);
        sync.advanceTo(GRAPH_VERSION, UUID.randomUUID().toString(), NODE_TIME.plusSeconds(1));
        syncRepository.saveAndFlush(sync);
        return new Fixture(project.getId());
    }

    private String node(
            int projectId,
            GraphNodeState state,
            String parentNodeId,
            String mergedIntoNodeId,
            long nodeVersion
    ) {
        String nodeId = UUID.randomUUID().toString();
        nodeRepository.saveAndFlush(ProjectNodeProjection.from(
                projectId,
                new ProjectGraphSnapshotNode(
                        nodeId,
                        null,
                        parentNodeId,
                        mergedIntoNodeId,
                        GraphNodeType.DECISION,
                        GraphNodeCategory.BACKEND,
                        state,
                        "title",
                        "content",
                        null,
                        nodeVersion,
                        NODE_TIME,
                        NODE_TIME
                ),
                NODE_TIME
        ));
        return nodeId;
    }

    private void assertDeleteError(
            int projectId,
            GraphNodeDeleteRequest request,
            com.ssafy.projectree.global.exception.ErrorCode expectedError
    ) {
        assertThatThrownBy(() -> service.deleteNodes(
                projectId,
                MEMBER_ID,
                request
        ))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(expectedError);
    }

    private void assertDeleteStorageEmpty() {
        assertThat(commandRepository.count()).isZero();
        assertThat(itemRepository.count()).isZero();
        assertThat(outboxRepository.count()).isZero();
    }

    private record Fixture(int projectId) {
    }
}
