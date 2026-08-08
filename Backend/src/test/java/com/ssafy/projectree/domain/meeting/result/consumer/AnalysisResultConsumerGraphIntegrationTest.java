package com.ssafy.projectree.domain.meeting.result.consumer;

import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.config.AnalysisResultConsumerProperties;
import com.ssafy.projectree.domain.meeting.result.graph.projection.AnalysisGraphProjectionApplier;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.meeting.result.graph.storage.GraphSnapshotLoader;
import com.ssafy.projectree.domain.meeting.result.graph.storage.RetryableGraphSnapshotDownloadException;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sqs.model.Message;
import software.amazon.awssdk.services.sqs.model.MessageSystemAttributeName;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ActiveProfiles("test")
@SpringBootTest(properties = {
        "spring.task.scheduling.enabled=false",
        "app.meeting-analysis.result-consumer.enabled=true",
        "app.meeting-analysis.result-consumer.queue-url=https://example.invalid/result-queue",
        "app.meeting-analysis.graph-snapshot.s3.enabled=true",
        "app.meeting-analysis.graph-snapshot.s3.expected-bucket=graph-bucket",
        "app.meeting-analysis.graph-snapshot.s3.region=ap-northeast-2"
})
class AnalysisResultConsumerGraphIntegrationTest {

    @MockitoBean private GoogleOAuthClient googleOAuthClient;
    @MockitoBean private NaverOAuthClient naverOAuthClient;
    @MockitoBean(name = "graphSnapshotS3Client") private S3Client s3Client;
    @MockitoBean private AnalysisResultSqsGateway sqsGateway;
    @MockitoBean private AnalysisResultConsumerScheduler scheduler;
    @MockitoBean private GraphSnapshotLoader snapshotLoader;
    @MockitoSpyBean private AnalysisGraphProjectionApplier projectionApplier;

    @Autowired private AnalysisResultConsumer consumer;
    @Autowired private AnalysisResultConsumerProperties consumerProperties;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private MeetingRepository meetingRepository;
    @Autowired private MeetingAnalysisCommandOutboxRepository commandRepository;
    @Autowired private MeetingAnalysisResultInboxRepository inboxRepository;
    @Autowired private ProjectGraphSyncRepository graphSyncRepository;
    @Autowired private ProjectNodeProjectionRepository nodeRepository;
    @Autowired private NodeEvidenceProjectionRepository evidenceRepository;
    @Autowired private MeetingAnalysisNotificationOutboxRepository notificationRepository;
    @Autowired private ObjectMapper objectMapper;

    @AfterEach
    void cleanUp() {
        inboxRepository.deleteAll();
        notificationRepository.deleteAll();
        evidenceRepository.deleteAll();
        nodeRepository.deleteAll();
        graphSyncRepository.deleteAll();
        commandRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void configuresActiveConsumerAndGatewayWhenQueueUrlIsConfigured() {
        assertThat(consumerProperties.enabled()).isTrue();
        assertThat(consumerProperties.queueUrl()).isEqualTo("https://example.invalid/result-queue");
        assertThat(consumer).isNotNull();
        assertThat(sqsGateway).isNotNull();
    }

    @Test
    void commitsActualGraphProcessingThenAcknowledgesMessage() throws Exception {
        Fixture fixture = fixture();
        AnalysisResultEventEnvelope event = event(fixture, UUID.randomUUID().toString());
        Message message = message(event, "normal");
        when(sqsGateway.receiveMessages()).thenReturn(List.of(message));
        when(snapshotLoader.load(any(), any())).thenReturn(snapshot(fixture, 1));

        consumer.consumeAvailable();

        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getNodeStatus())
                .isEqualTo(AnalysisTaskStatus.SUCCEEDED);
        assertThat(inboxRepository.count()).isEqualTo(1);
        assertThat(nodeRepository.countByProjectId(fixture.projectId())).isEqualTo(1);
        verify(sqsGateway).deleteMessage(message);
    }

    @Test
    void acknowledgesDuplicateWithoutLoadingSnapshotAgain() throws Exception {
        Fixture fixture = fixture();
        AnalysisResultEventEnvelope event = event(fixture, UUID.randomUUID().toString());
        Message first = message(event, "first");
        Message duplicate = message(event, "duplicate");
        when(sqsGateway.receiveMessages()).thenReturn(List.of(first), List.of(duplicate));
        when(snapshotLoader.load(any(), any())).thenReturn(snapshot(fixture, 1));

        consumer.consumeAvailable();
        consumer.consumeAvailable();

        verify(snapshotLoader, times(1)).load(any(), any());
        verify(sqsGateway).deleteMessage(first);
        verify(sqsGateway).deleteMessage(duplicate);
        assertThat(inboxRepository.count()).isEqualTo(1);
    }

    @Test
    void doesNotAcknowledgeRetryableSnapshotFailure() throws Exception {
        Fixture fixture = fixture();
        Message message = message(event(fixture, UUID.randomUUID().toString()), "retryable");
        when(sqsGateway.receiveMessages()).thenReturn(List.of(message));
        doThrow(new RetryableGraphSnapshotDownloadException("temporary", new IllegalStateException("network")))
                .when(snapshotLoader).load(any(), any());

        consumer.consumeAvailable();

        verify(sqsGateway, never()).deleteMessage(message);
        assertThat(inboxRepository.count()).isZero();
    }

    @Test
    void isolatesFailedMessageAndAcknowledgesFollowingNormalMessage() throws Exception {
        Fixture fixture = fixture();
        AnalysisResultEventEnvelope failingEvent = event(fixture, UUID.randomUUID().toString());
        AnalysisResultEventEnvelope normalEvent = event(fixture, UUID.randomUUID().toString());
        Message failing = message(failingEvent, "failing");
        Message normal = message(normalEvent, "normal");
        when(sqsGateway.receiveMessages()).thenReturn(List.of(failing, normal));
        when(snapshotLoader.load(any(), any())).thenReturn(snapshot(fixture, 1));
        doAnswer(invocation -> {
            AnalysisResultEventEnvelope incoming = invocation.getArgument(0);
            if (incoming.eventId().equals(failingEvent.eventId())) {
                throw new DataIntegrityViolationException("projection unavailable");
            }
            return invocation.callRealMethod();
        }).when(projectionApplier).apply(any(), any(), any());

        consumer.consumeAvailable();

        verify(sqsGateway, never()).deleteMessage(failing);
        verify(sqsGateway).deleteMessage(normal);
        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getNodeStatus())
                .isEqualTo(AnalysisTaskStatus.SUCCEEDED);
        assertThat(inboxRepository.count()).isEqualTo(1);
    }

    private Fixture fixture() {
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(17, ProjectRole.OWNER);
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);
        Meeting meeting = Meeting.create(project, creator, UUID.randomUUID().toString());
        meeting.confirmAnalysisOptions(false, true);
        meeting = meetingRepository.saveAndFlush(meeting);
        MeetingAnalysisCommandOutbox command = commandRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pending(
                        UUID.randomUUID(), meeting, MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                        "{\"command\":true}", 17, LocalDateTime.now()
                )
        );
        ProjectGraphSync sync = ProjectGraphSync.initial(
                project.getId(),
                Instant.parse("2026-08-05T00:00:00Z")
        );
        sync.acquireGraphOperation(
                command.getCommandId(),
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                Instant.parse("2026-08-05T00:00:01Z")
        );
        graphSyncRepository.saveAndFlush(sync);
        return new Fixture(project.getId(), meeting.getId(), command.getCommandId());
    }

    private AnalysisResultEventEnvelope event(Fixture fixture, String eventId) {
        return new AnalysisResultEventEnvelope(
                3, eventId, AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.parse("2026-08-05T00:00:00Z"), fixture.projectId(), fixture.meetingId(), fixture.commandId(),
                objectMapper.createObjectNode()
                        .put("sourceType", "MEETING_ANALYSIS")
                        .put("graphVersion", 1)
                        .set("snapshotRef", objectMapper.createObjectNode()
                                .put("bucket", "graph-bucket")
                                .put("objectKey", "graph-snapshots/test.json")
                                .put("contentType", "application/json")
                                .put("sizeBytes", 1)
                                .put("sha256", "a".repeat(64)))
        );
    }

    private Message message(AnalysisResultEventEnvelope event, String suffix) throws Exception {
        return Message.builder()
                .messageId("message-" + suffix)
                .receiptHandle("receipt-" + suffix)
                .body(objectMapper.writeValueAsString(event))
                .attributes(java.util.Map.of(MessageSystemAttributeName.APPROXIMATE_RECEIVE_COUNT, "1"))
                .build();
    }

    private ProjectGraphSnapshot snapshot(Fixture fixture, long graphVersion) {
        Instant now = Instant.parse("2026-08-05T00:00:00Z");
        String nodeId = UUID.randomUUID().toString();
        return new ProjectGraphSnapshot(
                1, fixture.projectId(), fixture.meetingId(), fixture.commandId(), graphVersion, now,
                List.of(new ProjectGraphSnapshotNode(nodeId, fixture.meetingId(), null, null,
                        GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE,
                        "title", "content", null, 1, now, now)),
                List.of(new ProjectGraphSnapshotEvidence(UUID.randomUUID().toString(), nodeId, fixture.meetingId(),
                        "quote", null, null, null, 1)),
                List.of()
        );
    }

    private record Fixture(int projectId, int meetingId, String commandId) {
    }
}
