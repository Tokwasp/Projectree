package com.ssafy.projectree.domain.meeting.result.graph.command;

import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;
import com.ssafy.projectree.domain.meeting.command.NodeContentUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.slf4j.LoggerFactory;
import org.springframework.test.util.ReflectionTestUtils;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class GraphNodeUpdateServiceTest {

    @Mock private ProjectRepository projectRepository;
    @Mock private ProjectMemberRepository memberRepository;
    @Mock private ProjectNodeProjectionRepository nodeRepository;
    @Mock private MeetingAnalysisCommandOutboxRepository outboxRepository;
    @Mock private ObjectMapper objectMapper;

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
                Clock.fixed(Instant.parse("2026-08-06T06:30:00Z"), ZoneOffset.UTC)
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
        when(projectRepository.existsById(1)).thenReturn(true);
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

        ArgumentCaptor<NodeContentUpdateRequestedCommand> commandCaptor =
                ArgumentCaptor.forClass(NodeContentUpdateRequestedCommand.class);
        verify(objectMapper).writeValueAsString(commandCaptor.capture());
        assertThat(commandCaptor.getValue().payload().title()).isEqualTo("SENSITIVE_NODE_TITLE");
        assertThat(commandCaptor.getValue().payload().content()).isNull();

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
    void stagesContentOnlyCommandWithoutLoggingContent() throws Exception {
        String nodeId = UUID.randomUUID().toString();
        ProjectNodeProjection projection = mock(ProjectNodeProjection.class);
        when(projection.getSourceNodeVersion()).thenReturn(3L);
        when(projectRepository.existsById(1)).thenReturn(true);
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
        when(projectRepository.existsById(1)).thenReturn(true);
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
        when(projectRepository.existsById(1)).thenReturn(true);
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

    private java.util.List<String> stagedLogs() {
        return logAppender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .filter(message -> message.contains("NODE_UPDATE_COMMAND_STAGED"))
                .toList();
    }
}
