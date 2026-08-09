package com.ssafy.projectree.domain.meeting.result.graph.command;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.ssafy.projectree.domain.meeting.command.NodeContentUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.command.NodeContentBatchUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateItem;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationErrorCode;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InOrder;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.slf4j.LoggerFactory;
import org.springframework.test.util.ReflectionTestUtils;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.doThrow;

@ExtendWith(MockitoExtension.class)
class GraphNodeUpdateServiceTest {

    @Mock private ProjectRepository projectRepository;
    @Mock private ProjectMemberRepository memberRepository;
    @Mock private ProjectNodeProjectionRepository nodeRepository;
    @Mock private MeetingAnalysisCommandOutboxRepository outboxRepository;
    @Mock private ObjectMapper objectMapper;
    @Mock private ProjectGraphOperationGuard graphOperationGuard;

    private GraphNodeUpdateService service;
    private Logger logger;
    private ListAppender<ILoggingEvent> logAppender;

    @BeforeEach
    void setUp() {
        service = new GraphNodeUpdateService(
                projectRepository,
                memberRepository,
                nodeRepository,
                outboxRepository,
                objectMapper,
                Clock.fixed(Instant.parse("2026-08-06T06:30:00Z"), ZoneOffset.UTC),
                graphOperationGuard
        );
        logger = (Logger) LoggerFactory.getLogger(GraphNodeUpdateService.class);
        logAppender = new ListAppender<>();
        logAppender.start();
        logger.addAppender(logAppender);
    }

    @AfterEach
    void tearDown() {
        logger.detachAppender(logAppender);
        logAppender.stop();
    }

    @Test
    void stagesMeetingIndependentCommandWithoutChangingProjection() throws Exception {
        String nodeId = UUID.randomUUID().toString();
        ProjectNodeProjection projection = mock(ProjectNodeProjection.class);
        when(projection.getSourceNodeVersion()).thenReturn(3L);
        when(projectRepository.findByIdForUpdate(1)).thenReturn(Optional.of(mock(Project.class)));
        when(memberRepository.existsByProjectIdAndMemberId(1, 15)).thenReturn(true);
        when(nodeRepository.findByNodeIdAndProjectId(nodeId, 1)).thenReturn(Optional.of(projection));
        when(objectMapper.writeValueAsString(any(NodeContentUpdateRequestedCommand.class)))
                .thenReturn("{\"commandType\":\"NODE_CONTENT_UPDATE_REQUESTED\"}");
        when(outboxRepository.saveAndFlush(any())).thenAnswer(invocation -> {
            MeetingAnalysisCommandOutbox outbox = invocation.getArgument(0);
            ReflectionTestUtils.setField(outbox, "id", 31);
            return outbox;
        });

        var response = service.update(
                1,
                nodeId,
                15,
                new NodeContentUpdateRequest("  SENSITIVE_NODE_TITLE  ", null, 3L)
        );

        ArgumentCaptor<MeetingAnalysisCommandOutbox> captor =
                ArgumentCaptor.forClass(MeetingAnalysisCommandOutbox.class);
        verify(outboxRepository).saveAndFlush(captor.capture());
        MeetingAnalysisCommandOutbox outbox = captor.getValue();
        assertThat(outbox.getMeeting()).isNull();
        assertThat(outbox.getTargetProjectId()).isEqualTo(1);
        assertThat(outbox.getTargetNodeId()).isEqualTo(nodeId);
        assertThat(response.status()).isEqualTo("PENDING");
        verify(graphOperationGuard).acquire(
                org.mockito.ArgumentMatchers.eq(1),
                any(),
                org.mockito.ArgumentMatchers.eq(
                        com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED
                ),
                any()
        );

        ArgumentCaptor<NodeContentUpdateRequestedCommand> commandCaptor =
                ArgumentCaptor.forClass(NodeContentUpdateRequestedCommand.class);
        verify(objectMapper).writeValueAsString(commandCaptor.capture());
        assertThat(commandCaptor.getValue().payload().title()).isEqualTo("SENSITIVE_NODE_TITLE");
        assertThat(commandCaptor.getValue().payload().content()).isNull();

        InOrder lockOrder = inOrder(projectRepository, nodeRepository);
        lockOrder.verify(projectRepository).findByIdForUpdate(1);
        lockOrder.verify(nodeRepository).findByNodeIdAndProjectId(nodeId, 1);

        assertThat(stagedLogs()).singleElement().satisfies(message -> {
            assertThat(message)
                    .contains("commandId=" + response.commandId())
                    .contains("commandType=NODE_CONTENT_UPDATE_REQUESTED")
                    .contains("outboxId=31")
                    .contains("projectId=1")
                    .contains("nodeId=" + nodeId)
                    .contains("requestedByMemberId=15")
                    .contains("expectedNodeVersion=3")
                    .contains("updateTitle=true")
                    .contains("updateContent=false")
                    .doesNotContain("SENSITIVE_NODE_TITLE");
        });
    }

    @Test
    void activeGraphOperationRejectsUpdateWithoutStagingOutbox() {
        String nodeId = UUID.randomUUID().toString();
        ProjectNodeProjection projection = mock(ProjectNodeProjection.class);
        when(projection.getSourceNodeVersion()).thenReturn(3L);
        when(projectRepository.findByIdForUpdate(1)).thenReturn(Optional.of(mock(Project.class)));
        when(memberRepository.existsByProjectIdAndMemberId(1, 15)).thenReturn(true);
        when(nodeRepository.findByNodeIdAndProjectId(nodeId, 1))
                .thenReturn(Optional.of(projection));
        doThrow(new CustomException(
                ProjectGraphOperationErrorCode.GRAPH_OPERATION_IN_PROGRESS
        )).when(graphOperationGuard).acquire(
                org.mockito.ArgumentMatchers.eq(1),
                any(),
                any(),
                any()
        );

        assertThatThrownBy(() -> service.update(
                1,
                nodeId,
                15,
                new NodeContentUpdateRequest("title", null, 3L)
        ))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(ProjectGraphOperationErrorCode.GRAPH_OPERATION_IN_PROGRESS);

        verify(outboxRepository, never()).saveAndFlush(any());
    }

    @Test
    void stagesContentOnlyCommandWithoutLoggingContent() throws Exception {
        String nodeId = UUID.randomUUID().toString();
        ProjectNodeProjection projection = mock(ProjectNodeProjection.class);
        when(projection.getSourceNodeVersion()).thenReturn(3L);
        when(projectRepository.findByIdForUpdate(1)).thenReturn(Optional.of(mock(Project.class)));
        when(memberRepository.existsByProjectIdAndMemberId(1, 15)).thenReturn(true);
        when(nodeRepository.findByNodeIdAndProjectId(nodeId, 1)).thenReturn(Optional.of(projection));
        when(objectMapper.writeValueAsString(any(NodeContentUpdateRequestedCommand.class)))
                .thenReturn("{\"commandType\":\"NODE_CONTENT_UPDATE_REQUESTED\"}");
        when(outboxRepository.saveAndFlush(any())).thenAnswer(invocation -> {
            MeetingAnalysisCommandOutbox outbox = invocation.getArgument(0);
            ReflectionTestUtils.setField(outbox, "id", 32);
            return outbox;
        });

        service.update(
                1,
                nodeId,
                15,
                new NodeContentUpdateRequest(null, "SENSITIVE_NODE_CONTENT", 3L)
        );

        assertThat(stagedLogs()).singleElement().satisfies(message -> assertThat(message)
                .contains("updateTitle=false")
                .contains("updateContent=true")
                .doesNotContain("SENSITIVE_NODE_CONTENT"));
    }

    @Test
    void rejectsEmptyOrConflictingRequestWithoutStagingCommand() {
        assertThatThrownBy(() -> service.update(
                1, UUID.randomUUID().toString(), 15,
                new NodeContentUpdateRequest(null, null, 3L)
        )).isInstanceOf(CustomException.class);

        String nodeId = UUID.randomUUID().toString();
        ProjectNodeProjection projection = mock(ProjectNodeProjection.class);
        when(projection.getSourceNodeVersion()).thenReturn(4L);
        when(projectRepository.findByIdForUpdate(1)).thenReturn(Optional.of(mock(Project.class)));
        when(memberRepository.existsByProjectIdAndMemberId(1, 15)).thenReturn(true);
        when(nodeRepository.findByNodeIdAndProjectId(nodeId, 1)).thenReturn(Optional.of(projection));

        assertThatThrownBy(() -> service.update(
                1, nodeId, 15, new NodeContentUpdateRequest("title", null, 3L)
        )).isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(GraphNodeUpdateErrorCode.NODE_VERSION_CONFLICT);
        verify(outboxRepository, never()).saveAndFlush(any());
        assertThat(stagedLogs()).isEmpty();
    }

    @Test
    void doesNotLogStagedWhenOutboxSaveFails() throws Exception {
        String nodeId = UUID.randomUUID().toString();
        ProjectNodeProjection projection = mock(ProjectNodeProjection.class);
        when(projection.getSourceNodeVersion()).thenReturn(3L);
        when(projectRepository.findByIdForUpdate(1)).thenReturn(Optional.of(mock(Project.class)));
        when(memberRepository.existsByProjectIdAndMemberId(1, 15)).thenReturn(true);
        when(nodeRepository.findByNodeIdAndProjectId(nodeId, 1)).thenReturn(Optional.of(projection));
        when(objectMapper.writeValueAsString(any(NodeContentUpdateRequestedCommand.class)))
                .thenReturn("{\"commandType\":\"NODE_CONTENT_UPDATE_REQUESTED\"}");
        when(outboxRepository.saveAndFlush(any()))
                .thenThrow(new IllegalStateException("database unavailable"));

        assertThatThrownBy(() -> service.update(
                1, nodeId, 15, new NodeContentUpdateRequest("title", null, 3L)
        )).isInstanceOf(IllegalStateException.class);

        assertThat(stagedLogs()).isEmpty();
    }

    @Test
    void rejectsMissingProjectBeforeNodeLookup() {
        when(projectRepository.findByIdForUpdate(1)).thenReturn(Optional.empty());

        assertThatThrownBy(() -> service.update(
                1,
                UUID.randomUUID().toString(),
                15,
                new NodeContentUpdateRequest("title", null, 3L)
        ))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);

        verify(nodeRepository, never()).findByNodeIdAndProjectId(any(), any(Integer.class));
        verify(outboxRepository, never()).saveAndFlush(any());
    }

    @Test
    void stagesOneV2CommandForAllChangedBatchNodes() throws Exception {
        String firstNodeId = UUID.randomUUID().toString();
        String secondNodeId = UUID.randomUUID().toString();
        ProjectNodeProjection firstNode = activeNode(firstNodeId, 3, "old first");
        ProjectNodeProjection secondNode = activeNode(secondNodeId, 7, "old second");
        when(projectRepository.findByIdForUpdate(1))
                .thenReturn(Optional.of(mock(Project.class)));
        when(memberRepository.existsByProjectIdAndMemberId(1, 15)).thenReturn(true);
        when(nodeRepository.findAllByProjectIdAndNodeIdIn(1, List.of(
                firstNodeId, secondNodeId
        ))).thenReturn(List.of(firstNode, secondNode));
        when(objectMapper.writeValueAsString(any(NodeContentBatchUpdateRequestedCommand.class)))
                .thenReturn("{\"commandSchemaVersion\":2}");
        when(outboxRepository.saveAndFlush(any())).thenAnswer(invocation -> {
            MeetingAnalysisCommandOutbox outbox = invocation.getArgument(0);
            ReflectionTestUtils.setField(outbox, "id", 41);
            return outbox;
        });

        var response = service.updateBatch(
                1,
                15,
                new BatchNodeContentUpdateRequest(List.of(
                        new BatchNodeContentUpdateItem(firstNodeId, " new first ", 3L),
                        new BatchNodeContentUpdateItem(secondNodeId, "new second", 7L)
                ))
        );

        assertThat(response.commandId()).isNotNull();
        assertThat(response.requestedNodeCount()).isEqualTo(2);
        assertThat(response.changedNodeCount()).isEqualTo(2);
        assertThat(response.status()).isEqualTo("PENDING");
        verify(graphOperationGuard, times(1)).acquire(
                org.mockito.ArgumentMatchers.eq(1),
                org.mockito.ArgumentMatchers.eq(response.commandId()),
                org.mockito.ArgumentMatchers.eq(
                        com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED
                ),
                any()
        );
        verify(outboxRepository, times(1)).saveAndFlush(any());

        ArgumentCaptor<MeetingAnalysisCommandOutbox> outboxCaptor =
                ArgumentCaptor.forClass(MeetingAnalysisCommandOutbox.class);
        verify(outboxRepository).saveAndFlush(outboxCaptor.capture());
        assertThat(outboxCaptor.getValue().getTargetProjectId()).isEqualTo(1);
        assertThat(outboxCaptor.getValue().getTargetNodeId()).isNull();

        ArgumentCaptor<NodeContentBatchUpdateRequestedCommand> commandCaptor =
                ArgumentCaptor.forClass(NodeContentBatchUpdateRequestedCommand.class);
        verify(objectMapper).writeValueAsString(commandCaptor.capture());
        NodeContentBatchUpdateRequestedCommand command = commandCaptor.getValue();
        assertThat(command.commandSchemaVersion()).isEqualTo(2);
        assertThat(command.commandId()).isEqualTo(response.commandId());
        assertThat(command.payload().requestedByMemberId()).isEqualTo(15);
        assertThat(command.payload().nodes())
                .extracting(
                        NodeContentBatchUpdateRequestedCommand.NodeUpdate::nodeId,
                        NodeContentBatchUpdateRequestedCommand.NodeUpdate::expectedNodeVersion,
                        NodeContentBatchUpdateRequestedCommand.NodeUpdate::title
                )
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple(firstNodeId, 3L, "new first"),
                        org.assertj.core.groups.Tuple.tuple(secondNodeId, 7L, "new second")
                );
    }

    @Test
    void validatesEveryVersionBeforeFilteringNoChangeNodes() {
        String unchangedNodeId = UUID.randomUUID().toString();
        String conflictingNodeId = UUID.randomUUID().toString();
        ProjectNodeProjection unchangedNode = activeNode(
                unchangedNodeId, 3, "same title"
        );
        ProjectNodeProjection conflictingNode = activeNode(
                conflictingNodeId, 8, "old title"
        );
        when(projectRepository.findByIdForUpdate(1))
                .thenReturn(Optional.of(mock(Project.class)));
        when(memberRepository.existsByProjectIdAndMemberId(1, 15)).thenReturn(true);
        when(nodeRepository.findAllByProjectIdAndNodeIdIn(1, List.of(
                unchangedNodeId, conflictingNodeId
        ))).thenReturn(List.of(unchangedNode, conflictingNode));

        assertThatThrownBy(() -> service.updateBatch(
                1,
                15,
                new BatchNodeContentUpdateRequest(List.of(
                        new BatchNodeContentUpdateItem(
                                unchangedNodeId, "same title", 3L
                        ),
                        new BatchNodeContentUpdateItem(
                                conflictingNodeId, "new title", 7L
                        )
                ))
        )).isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(GraphNodeUpdateErrorCode.NODE_VERSION_CONFLICT);

        verify(graphOperationGuard, times(1)).acquire(any(Integer.class), any(), any(), any());
        verify(outboxRepository, never()).saveAndFlush(any());
    }

    @Test
    void sendsOnlyChangedNodesAndReleasesGuardWhenAllAreNoChange() throws Exception {
        String changedNodeId = UUID.randomUUID().toString();
        String unchangedNodeId = UUID.randomUUID().toString();
        ProjectNodeProjection changedNode = activeNode(changedNodeId, 3, "old");
        ProjectNodeProjection unchangedNode = activeNode(unchangedNodeId, 7, "same");
        when(projectRepository.findByIdForUpdate(1))
                .thenReturn(Optional.of(mock(Project.class)));
        when(memberRepository.existsByProjectIdAndMemberId(1, 15)).thenReturn(true);
        when(nodeRepository.findAllByProjectIdAndNodeIdIn(1, List.of(
                changedNodeId, unchangedNodeId
        ))).thenReturn(List.of(changedNode, unchangedNode));
        when(objectMapper.writeValueAsString(any(NodeContentBatchUpdateRequestedCommand.class)))
                .thenReturn("{\"commandSchemaVersion\":2}");
        when(outboxRepository.saveAndFlush(any())).thenAnswer(invocation -> invocation.getArgument(0));

        service.updateBatch(1, 15, new BatchNodeContentUpdateRequest(List.of(
                new BatchNodeContentUpdateItem(changedNodeId, "new", 3L),
                new BatchNodeContentUpdateItem(unchangedNodeId, "same", 7L)
        )));

        ArgumentCaptor<NodeContentBatchUpdateRequestedCommand> commandCaptor =
                ArgumentCaptor.forClass(NodeContentBatchUpdateRequestedCommand.class);
        verify(objectMapper).writeValueAsString(commandCaptor.capture());
        assertThat(commandCaptor.getValue().payload().nodes())
                .extracting(NodeContentBatchUpdateRequestedCommand.NodeUpdate::nodeId)
                .containsExactly(changedNodeId);

        org.mockito.Mockito.reset(outboxRepository, objectMapper, graphOperationGuard);
        ProjectGraphSync sync = mock(ProjectGraphSync.class);
        when(graphOperationGuard.acquire(any(Integer.class), any(), any(), any()))
                .thenReturn(sync);
        when(nodeRepository.findAllByProjectIdAndNodeIdIn(1, List.of(unchangedNodeId)))
                .thenReturn(List.of(unchangedNode));

        var noChange = service.updateBatch(
                1,
                15,
                new BatchNodeContentUpdateRequest(List.of(
                        new BatchNodeContentUpdateItem(unchangedNodeId, "same", 7L)
                ))
        );

        assertThat(noChange.commandId()).isNull();
        assertThat(noChange.requestedNodeCount()).isEqualTo(1);
        assertThat(noChange.changedNodeCount()).isZero();
        assertThat(noChange.status()).isEqualTo("NO_CHANGE");
        verify(outboxRepository, never()).saveAndFlush(any());
        verify(graphOperationGuard).release(
                org.mockito.ArgumentMatchers.eq(sync),
                any(String.class),
                org.mockito.ArgumentMatchers.eq("NO_CHANGE")
        );
    }

    @Test
    void rejectsDuplicateBatchNodeIdsBeforeDatabaseAccess() {
        String nodeId = UUID.randomUUID().toString();
        BatchNodeContentUpdateRequest request = new BatchNodeContentUpdateRequest(List.of(
                new BatchNodeContentUpdateItem(nodeId, "first", 3L),
                new BatchNodeContentUpdateItem(nodeId, "second", 3L)
        ));

        assertThatThrownBy(() -> service.updateBatch(1, 15, request))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(GraphNodeUpdateErrorCode.NODE_UPDATE_DUPLICATE_NODE_ID);

        verify(projectRepository, never()).findByIdForUpdate(any(Integer.class));
        verify(outboxRepository, never()).saveAndFlush(any());
    }

    private ProjectNodeProjection activeNode(
            String nodeId,
            long sourceNodeVersion,
            String title
    ) {
        ProjectNodeProjection node = mock(ProjectNodeProjection.class);
        when(node.getNodeId()).thenReturn(nodeId);
        when(node.getSourceNodeVersion()).thenReturn(sourceNodeVersion);
        lenient().when(node.getTitle()).thenReturn(title);
        when(node.getGraphState()).thenReturn(GraphNodeState.ACTIVE);
        return node;
    }

    private java.util.List<String> stagedLogs() {
        return logAppender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .filter(message -> message.contains("NODE_UPDATE_COMMAND_STAGED"))
                .toList();
    }
}
