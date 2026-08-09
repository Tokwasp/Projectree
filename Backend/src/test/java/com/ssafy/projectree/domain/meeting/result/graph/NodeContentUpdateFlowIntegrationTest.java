package com.ssafy.projectree.domain.meeting.result.graph;

import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.outbox.publisher.CommandOutboxPublisher;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.sender.CommandSendResult;
import com.ssafy.projectree.domain.meeting.outbox.sender.MeetingAnalysisCommandSender;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.command.GraphNodeCommandController;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateAcceptedResponse;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateItem;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateResponse;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.meeting.result.graph.storage.GraphSnapshotLoader;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultEventProcessor;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultProcessingOutcome;
import com.ssafy.projectree.domain.meeting.result.graph.command.GraphNodeUpdateErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;
import software.amazon.awssdk.services.s3.S3Client;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ActiveProfiles("test")
@SpringBootTest(properties = {
        "app.scheduling.enabled=false",
        "app.meeting-analysis.publisher.enabled=true",
        "app.meeting-analysis.publisher.queue-url=https://example.invalid/command-queue",
        "app.meeting-analysis.publisher.batch-size=20",
        "app.meeting-analysis.publisher.max-attempts=3",
        "app.meeting-analysis.graph-snapshot.s3.enabled=true",
        "app.meeting-analysis.graph-snapshot.s3.expected-bucket=graph-bucket",
        "app.meeting-analysis.graph-snapshot.s3.region=ap-northeast-2"
})
class NodeContentUpdateFlowIntegrationTest {

    private static final int MEMBER_ID = 15;
    private static final Instant NOW = Instant.parse("2026-08-06T06:30:02Z");

    @MockitoBean private GoogleOAuthClient googleOAuthClient;
    @MockitoBean private NaverOAuthClient naverOAuthClient;
    @MockitoBean private RedisMessageListenerContainer redisMessageListenerContainer;
    @MockitoBean private MeetingAnalysisCommandSender sender;
    @MockitoBean(name = "graphSnapshotS3Client") private S3Client s3Client;
    @MockitoBean private GraphSnapshotLoader snapshotLoader;

    @Autowired private ObjectMapper objectMapper;
    @Autowired private GraphNodeCommandController commandController;
    @Autowired private CommandOutboxPublisher publisher;
    @Autowired private AnalysisResultEventProcessor resultProcessor;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private MeetingRepository meetingRepository;
    @Autowired private MeetingAnalysisCommandOutboxRepository commandRepository;
    @Autowired private MeetingAnalysisResultInboxRepository inboxRepository;
    @Autowired private MeetingAnalysisNotificationOutboxRepository notificationRepository;
    @Autowired private ProjectGraphSyncRepository syncRepository;
    @Autowired private ProjectNodeProjectionRepository nodeRepository;
    @Autowired private NodeEvidenceProjectionRepository evidenceRepository;

    @AfterEach
    void cleanUp() {
        inboxRepository.deleteAll();
        notificationRepository.deleteAll();
        evidenceRepository.deleteAll();
        nodeRepository.deleteAll();
        syncRepository.deleteAll();
        commandRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void persistsPublishesAndAppliesNodeUpdateWithIdempotencyAndRollbackSafety()
            throws Exception {
        Fixture fixture = fixture();

        ResponseEntity<com.ssafy.projectree.global.response.ApiResponse<
                NodeContentUpdateAcceptedResponse>> response = commandController.update(
                fixture.projectId(),
                fixture.nodeId(),
                new NodeContentUpdateRequest("수정된 제목", "수정된 내용", 3L),
                com.ssafy.projectree.domain.member.LoginMember.builder()
                        .id(MEMBER_ID)
                        .name("member")
                        .email("member@example.com")
                        .build()
        );
        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.ACCEPTED);
        assertThat(response.getBody()).isNotNull();
        String commandId = response.getBody().getData().commandId().toString();

        MeetingAnalysisCommandOutbox staged = commandRepository
                .findByCommandId(commandId)
                .orElseThrow();
        assertThat(staged.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PENDING);
        assertThat(staged.getMeeting()).isNull();
        assertThat(staged.getTargetProjectId()).isEqualTo(fixture.projectId());
        assertThat(staged.getTargetNodeId()).isEqualTo(fixture.nodeId());
        assertProjection(fixture.nodeId(), "기존 제목", "기존 내용", 3);

        when(sender.send(commandId, staged.getPayload()))
                .thenReturn(new CommandSendResult("sqs-message-id"));
        assertThat(publisher.publishAvailable()).isEqualTo(1);
        verify(sender).send(commandId, staged.getPayload());
        assertThat(commandRepository.findByCommandId(commandId).orElseThrow().getStatus())
                .isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHED);

        AnalysisResultEventEnvelope appliedEvent = event(
                fixture.projectId(), commandId, UUID.randomUUID().toString(), 11
        );
        ProjectGraphSnapshot appliedSnapshot = snapshot(
                fixture.projectId(),
                commandId,
                11,
                List.of(node(fixture.nodeId(), 4, "수정된 제목", "수정된 내용"))
        );
        when(snapshotLoader.load(any(), any())).thenReturn(appliedSnapshot);

        assertThat(resultProcessor.process(appliedEvent))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);
        assertProjection(fixture.nodeId(), "수정된 제목", "수정된 내용", 4);
        ProjectGraphSync updatedSync = syncRepository.findById(fixture.projectId()).orElseThrow();
        assertThat(updatedSync.getCurrentGraphVersion()).isEqualTo(11);
        assertThat(updatedSync.getLastCommandId()).isEqualTo(commandId);
        assertThat(updatedSync.hasActiveCommand()).isFalse();
        assertThat(inboxRepository.findAll())
                .filteredOn(inbox -> inbox.getEventId().equals(appliedEvent.eventId()))
                .singleElement()
                .extracting(inbox -> inbox.getMeetingId())
                .isNull();
        assertThat(meetingRepository.count()).isZero();
        assertThat(notificationRepository.count()).isZero();

        assertThat(resultProcessor.process(appliedEvent))
                .isEqualTo(AnalysisResultProcessingOutcome.DUPLICATE);

        AnalysisResultEventEnvelope staleEvent = event(
                fixture.projectId(), commandId, UUID.randomUUID().toString(), 10
        );
        when(snapshotLoader.load(any(), any())).thenReturn(snapshot(
                fixture.projectId(), commandId, 10, List.of()
        ));
        assertThat(resultProcessor.process(staleEvent))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);
        assertProjection(fixture.nodeId(), "수정된 제목", "수정된 내용", 4);

        long inboxCountBeforeInvalid = inboxRepository.count();
        AnalysisResultEventEnvelope invalidEvent = event(
                fixture.projectId(), commandId, UUID.randomUUID().toString(), 12
        );
        when(snapshotLoader.load(any(), any())).thenReturn(snapshot(
                fixture.projectId(), commandId, 12,
                List.of(node(UUID.randomUUID().toString(), 4, "수정된 제목", "수정된 내용"))
        ));

        assertThatThrownBy(() -> resultProcessor.process(invalidEvent))
                .isInstanceOf(AnalysisResultContractException.class);
        assertProjection(fixture.nodeId(), "수정된 제목", "수정된 내용", 4);
        assertThat(syncRepository.findById(fixture.projectId()).orElseThrow().getCurrentGraphVersion())
                .isEqualTo(11);
        assertThat(inboxRepository.count()).isEqualTo(inboxCountBeforeInvalid);
        assertThat(inboxRepository.existsByEventId(invalidEvent.eventId())).isFalse();
    }

    @Test
    void batchConflictRollsBackGuardAndNoChangeRequestCanRunNext() {
        Fixture fixture = fixture();
        BatchNodeContentUpdateRequest conflictRequest =
                new BatchNodeContentUpdateRequest(List.of(
                        new BatchNodeContentUpdateItem(
                                fixture.nodeId(), "new title", 2L
                        )
                ));

        assertThatThrownBy(() -> commandController.updateBatch(
                fixture.projectId(),
                conflictRequest,
                loginMember()
        )).isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(GraphNodeUpdateErrorCode.NODE_VERSION_CONFLICT);

        assertThat(commandRepository.count()).isZero();
        ProjectGraphSync syncAfterConflict = syncRepository
                .findById(fixture.projectId())
                .orElseThrow();
        assertThat(syncAfterConflict.hasActiveCommand()).isFalse();

        ResponseEntity<com.ssafy.projectree.global.response.ApiResponse<
                BatchNodeContentUpdateResponse>> noChangeResponse =
                commandController.updateBatch(
                        fixture.projectId(),
                        new BatchNodeContentUpdateRequest(List.of(
                                new BatchNodeContentUpdateItem(
                                        fixture.nodeId(), "기존 제목", 3L
                                )
                        )),
                        loginMember()
                );

        assertThat(noChangeResponse.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(noChangeResponse.getBody()).isNotNull();
        assertThat(noChangeResponse.getBody().getData().status()).isEqualTo("NO_CHANGE");
        assertThat(commandRepository.count()).isZero();
        assertThat(syncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isFalse();
    }

    @Test
    void rejectedNodeContentUpdateKeepsProjectionAndGraphVersionAndIsIdempotent() {
        Fixture fixture = fixture();
        ResponseEntity<com.ssafy.projectree.global.response.ApiResponse<
                BatchNodeContentUpdateResponse>> response = commandController.updateBatch(
                fixture.projectId(),
                new BatchNodeContentUpdateRequest(List.of(
                        new BatchNodeContentUpdateItem(
                                fixture.nodeId(), "수정 제목", 3L
                        )
                )),
                loginMember()
        );
        String commandId = response.getBody().getData().commandId().toString();
        String eventId = UUID.randomUUID().toString();
        AnalysisResultEventEnvelope rejectedEvent = new AnalysisResultEventEnvelope(
                3,
                eventId,
                AnalysisResultEventType.NODE_CONTENT_UPDATE_REJECTED,
                NOW,
                fixture.projectId(),
                null,
                commandId,
                objectMapper.createObjectNode()
                        .put("sourceType", "NODE_CONTENT_UPDATE")
                        .put("reasonCode", "NODE_VERSION_CONFLICT")
                        .put("failedNodeId", fixture.nodeId())
        );

        assertThat(resultProcessor.process(rejectedEvent))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);
        assertProjection(fixture.nodeId(), "기존 제목", "기존 내용", 3);
        ProjectGraphSync rejectedSync = syncRepository
                .findById(fixture.projectId())
                .orElseThrow();
        assertThat(rejectedSync.getCurrentGraphVersion()).isEqualTo(10);
        assertThat(rejectedSync.hasActiveCommand()).isFalse();

        assertThat(resultProcessor.process(rejectedEvent))
                .isEqualTo(AnalysisResultProcessingOutcome.DUPLICATE);
        assertThat(inboxRepository.findAll())
                .filteredOn(inbox -> inbox.getEventId().equals(eventId))
                .hasSize(1);
    }

    @Test
    void commandLevelNodeUpdateRejectionDoesNotRequireFailedNodeId() {
        Fixture fixture = fixture();
        ResponseEntity<com.ssafy.projectree.global.response.ApiResponse<
                BatchNodeContentUpdateResponse>> response = commandController.updateBatch(
                fixture.projectId(),
                new BatchNodeContentUpdateRequest(List.of(
                        new BatchNodeContentUpdateItem(
                                fixture.nodeId(), "수정 제목", 3L
                        )
                )),
                loginMember()
        );
        String commandId = response.getBody().getData().commandId().toString();
        AnalysisResultEventEnvelope rejectedEvent = new AnalysisResultEventEnvelope(
                3,
                UUID.randomUUID().toString(),
                AnalysisResultEventType.NODE_CONTENT_UPDATE_REJECTED,
                NOW,
                fixture.projectId(),
                null,
                commandId,
                objectMapper.createObjectNode()
                        .put("sourceType", "NODE_CONTENT_UPDATE")
                        .put("reasonCode", "GRAPH_SNAPSHOT_TOO_LARGE")
        );

        assertThat(resultProcessor.process(rejectedEvent))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);

        ProjectGraphSync sync = syncRepository
                .findById(fixture.projectId())
                .orElseThrow();
        assertThat(sync.getCurrentGraphVersion()).isEqualTo(10);
        assertThat(sync.hasActiveCommand()).isFalse();
        assertProjection(fixture.nodeId(), "기존 제목", "기존 내용", 3);
    }

    @Test
    void nodeSpecificUpdateRejectionRequiresFailedNodeId() {
        Fixture fixture = fixture();
        ResponseEntity<com.ssafy.projectree.global.response.ApiResponse<
                BatchNodeContentUpdateResponse>> response = commandController.updateBatch(
                fixture.projectId(),
                new BatchNodeContentUpdateRequest(List.of(
                        new BatchNodeContentUpdateItem(
                                fixture.nodeId(), "수정 제목", 3L
                        )
                )),
                loginMember()
        );
        String commandId = response.getBody().getData().commandId().toString();
        AnalysisResultEventEnvelope invalidEvent = new AnalysisResultEventEnvelope(
                3,
                UUID.randomUUID().toString(),
                AnalysisResultEventType.NODE_CONTENT_UPDATE_REJECTED,
                NOW,
                fixture.projectId(),
                null,
                commandId,
                objectMapper.createObjectNode()
                        .put("sourceType", "NODE_CONTENT_UPDATE")
                        .put("reasonCode", "NODE_VERSION_CONFLICT")
        );

        assertThatThrownBy(() -> resultProcessor.process(invalidEvent))
                .isInstanceOf(AnalysisResultContractException.class);

        ProjectGraphSync sync = syncRepository
                .findById(fixture.projectId())
                .orElseThrow();
        assertThat(sync.hasActiveCommand()).isTrue();
        assertThat(sync.getActiveCommandId()).isEqualTo(commandId);
        assertThat(inboxRepository.existsByEventId(invalidEvent.eventId())).isFalse();
        assertProjection(fixture.nodeId(), "기존 제목", "기존 내용", 3);
    }

    private Fixture fixture() {
        Project project = Project.builder().title("project").content("content").build();
        project.addMember(ProjectMember.createMember(MEMBER_ID, ProjectRole.OWNER));
        project = projectRepository.saveAndFlush(project);

        String nodeId = UUID.randomUUID().toString();
        nodeRepository.saveAndFlush(ProjectNodeProjection.from(
                project.getId(),
                node(nodeId, 3, "기존 제목", "기존 내용"),
                NOW.minusSeconds(10)
        ));
        ProjectGraphSync sync = ProjectGraphSync.initial(
                project.getId(), NOW.minusSeconds(10)
        );
        sync.advanceTo(10, UUID.randomUUID().toString(), NOW.minusSeconds(10));
        syncRepository.saveAndFlush(sync);
        return new Fixture(project.getId(), nodeId);
    }

    private com.ssafy.projectree.domain.member.LoginMember loginMember() {
        return com.ssafy.projectree.domain.member.LoginMember.builder()
                .id(MEMBER_ID)
                .name("member")
                .email("member@example.com")
                .build();
    }

    private AnalysisResultEventEnvelope event(
            int projectId,
            String commandId,
            String eventId,
            long graphVersion
    ) {
        return new AnalysisResultEventEnvelope(
                3,
                eventId,
                AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                NOW,
                projectId,
                null,
                commandId,
                objectMapper.createObjectNode()
                        .put("sourceType", "NODE_CONTENT_UPDATE")
                        .put("graphVersion", graphVersion)
                        .set("snapshotRef", objectMapper.createObjectNode()
                                .put("bucket", "graph-bucket")
                                .put("objectKey", "graph-snapshots/node-update.json")
                                .put("contentType", "application/json")
                                .put("sizeBytes", 1)
                                .put("sha256", "a".repeat(64)))
        );
    }

    private ProjectGraphSnapshot snapshot(
            int projectId,
            String commandId,
            long graphVersion,
            List<ProjectGraphSnapshotNode> nodes
    ) {
        return new ProjectGraphSnapshot(
                1,
                projectId,
                null,
                commandId,
                graphVersion,
                NOW,
                nodes,
                List.of(),
                List.of()
        );
    }

    private ProjectGraphSnapshotNode node(
            String nodeId,
            long version,
            String title,
            String content
    ) {
        return new ProjectGraphSnapshotNode(
                nodeId,
                null,
                null,
                null,
                GraphNodeType.DECISION,
                GraphNodeCategory.BACKEND,
                GraphNodeState.ACTIVE,
                title,
                content,
                null,
                version,
                NOW.minusSeconds(100),
                NOW
        );
    }

    private void assertProjection(
            String nodeId,
            String title,
            String content,
            long version
    ) {
        ProjectNodeProjection node = nodeRepository.findById(nodeId).orElseThrow();
        assertThat(node.getTitle()).isEqualTo(title);
        assertThat(node.getContent()).isEqualTo(content);
        assertThat(node.getSourceNodeVersion()).isEqualTo(version);
    }

    private record Fixture(int projectId, String nodeId) {
    }
}
