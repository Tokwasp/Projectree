package com.ssafy.projectree.domain.meeting.smoke;

import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisRequestedCommand;
import com.ssafy.projectree.domain.meeting.dto.request.MeetingAnalysisRequest;
import com.ssafy.projectree.domain.meeting.dto.response.MeetingAnalysisRequestResponse;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.outbox.publisher.CommandOutboxPublisher;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.consumer.AnalysisResultConsumer;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.query.GraphQueryService;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphLinkSource;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotEvidence;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.meeting.result.summary.repository.MeetingSummaryProjectionRepository;
import com.ssafy.projectree.domain.meeting.service.MeetingAnalysisRequestService;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.ChangeMessageVisibilityRequest;
import software.amazon.awssdk.services.sqs.model.DeleteMessageRequest;
import software.amazon.awssdk.services.sqs.model.GetQueueAttributesRequest;
import software.amazon.awssdk.services.sqs.model.QueueAttributeName;
import software.amazon.awssdk.services.sqs.model.ReceiveMessageRequest;
import software.amazon.awssdk.services.sqs.model.SendMessageRequest;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Duration;
import java.time.Instant;
import java.util.HexFormat;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

/**
 * Opt-in AWS smoke test.
 *
 * <p>It uses H2 for Java persistence but real SQS/S3 resources for transport:</p>
 * <ol>
 *   <li>Java creates an analysis command outbox and publishes it to Command SQS.</li>
 *   <li>This test acts as the Python worker, receives the command, uploads a graph snapshot to S3,
 *       and sends summary/graph result events to Result SQS.</li>
 *   <li>The real Java result consumer receives the events and updates the H2 projections.</li>
 * </ol>
 *
 * <p>Run only while the real Python worker and Java result consumer are stopped. Both configured
 * queues must be empty before the test starts.</p>
 */
@Tag("smoke")
@Tag("meeting-analysis-aws-smoke")
@ActiveProfiles("test")
@SpringBootTest(properties = {
        "spring.task.scheduling.enabled=false",
        "app.meeting-analysis.publisher.enabled=true",
        "app.meeting-analysis.publisher.batch-size=1",
        "app.meeting-analysis.publisher.max-attempts=3",
        "app.meeting-analysis.publisher.lease-duration-seconds=30",
        "app.meeting-analysis.publisher.api-call-attempt-timeout-seconds=5",
        "app.meeting-analysis.publisher.api-call-timeout-seconds=10",
        "app.meeting-analysis.result-consumer.enabled=true",
        "app.meeting-analysis.result-consumer.wait-time-seconds=1",
        "app.meeting-analysis.result-consumer.max-number-of-messages=1",
        "app.meeting-analysis.graph-snapshot.s3.enabled=true"
})
class MeetingAnalysisAwsE2ESmokeTest {

    private static final String COMMAND_QUEUE_URL = requiredEnv("MEETING_ANALYSIS_COMMAND_QUEUE_URL");
    private static final String RESULT_QUEUE_URL = requiredEnv("AWS_ANALYSIS_RESULT_QUEUE_URL");
    private static final String SNAPSHOT_BUCKET = requiredEnv("AWS_ANALYSIS_RESULT_BUCKET");
    private static final String SNAPSHOT_PREFIX = normalizedPrefix(
            envOrDefault("MEETING_ANALYSIS_GRAPH_SNAPSHOT_S3_PREFIX", "graph-snapshots/")
    );
    private static final String REGION = envOrDefault("AWS_REGION", "ap-northeast-2");

    @DynamicPropertySource
    static void awsProperties(DynamicPropertyRegistry registry) {
        registry.add("app.meeting-analysis.publisher.queue-url", () -> COMMAND_QUEUE_URL);
        registry.add("app.meeting-analysis.publisher.region", () -> REGION);
        registry.add("app.meeting-analysis.result-consumer.queue-url", () -> RESULT_QUEUE_URL);
        registry.add("app.meeting-analysis.result-consumer.region", () -> REGION);
        registry.add("app.meeting-analysis.graph-snapshot.s3.expected-bucket", () -> SNAPSHOT_BUCKET);
        registry.add("app.meeting-analysis.graph-snapshot.s3.allowed-object-key-prefix", () -> SNAPSHOT_PREFIX);
        registry.add("app.meeting-analysis.graph-snapshot.s3.region", () -> REGION);
    }

    @MockitoBean private GoogleOAuthClient googleOAuthClient;
    @MockitoBean private NaverOAuthClient naverOAuthClient;

    @Autowired private MeetingAnalysisRequestService requestService;
    @Autowired private CommandOutboxPublisher commandPublisher;
    @Autowired private AnalysisResultConsumer resultConsumer;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private MeetingRepository meetingRepository;
    @Autowired private MeetingAnalysisCommandOutboxRepository commandRepository;
    @Autowired private MeetingAnalysisResultInboxRepository inboxRepository;
    @Autowired private MeetingSummaryProjectionRepository summaryRepository;
    @Autowired private ProjectNodeProjectionRepository nodeRepository;
    @Autowired private NodeEvidenceProjectionRepository evidenceRepository;
    @Autowired private ProjectGraphSyncRepository graphSyncRepository;
    @Autowired private GraphQueryService graphQueryService;
    @Autowired private ObjectMapper objectMapper;
    @Autowired private SqsClient meetingAnalysisSqsClient;
    @Autowired @Qualifier("graphSnapshotS3Client") private S3Client graphSnapshotS3Client;

    private String testCommandId;
    private String summaryEventId;
    private String graphEventId;
    private String snapshotObjectKey;

    @BeforeEach
    void requireExclusiveEmptyQueues() {
        assertQueueEmpty(COMMAND_QUEUE_URL, "Command");
        assertQueueEmpty(RESULT_QUEUE_URL, "Result");
    }

    @AfterEach
    void cleanExternalArtifacts() {
        deleteMatchingMessages(COMMAND_QUEUE_URL);
        deleteMatchingMessages(RESULT_QUEUE_URL);
        if (snapshotObjectKey != null) {
            graphSnapshotS3Client.deleteObject(DeleteObjectRequest.builder()
                    .bucket(SNAPSHOT_BUCKET)
                    .key(snapshotObjectKey)
                    .build());
        }
    }

    @Test
    void roundTripsJavaCommandThroughFakePythonAndBackIntoJavaProjection() throws Exception {
        int memberId = 900_000 + Math.abs(UUID.randomUUID().hashCode() % 90_000);
        Project project = Project.builder()
                .title("AWS E2E smoke project")
                .content("temporary H2 fixture")
                .build();
        ProjectMember owner = ProjectMember.createMember(memberId, ProjectRole.OWNER);
        project.addMember(owner);
        project = projectRepository.saveAndFlush(project);

        String roomName = UUID.randomUUID().toString();
        Meeting meeting = meetingRepository.saveAndFlush(Meeting.create(project, owner, roomName));

        MeetingAnalysisRequestResponse requestResponse = requestService.requestAnalysis(
                project.getId(), roomName, memberId, new MeetingAnalysisRequest(true, true)
        );
        testCommandId = requestResponse.commandId().toString();

        assertEquals(1, commandPublisher.publishAvailable());
        assertEquals(
                MeetingAnalysisOutboxStatus.PUBLISHED,
                commandRepository.findByCommandIdWithMeetingAndProject(testCommandId)
                        .orElseThrow()
                        .getStatus()
        );

        // Fake Python: consume the exact command emitted by Java.
        ReceivedCommand received = receiveTargetCommand(Duration.ofSeconds(30));
        MeetingAnalysisRequestedCommand command = objectMapper.readValue(
                received.body(), MeetingAnalysisRequestedCommand.class
        );
        assertEquals(testCommandId, command.commandId().toString());
        assertEquals(project.getId(), command.projectId());
        assertEquals(meeting.getId(), command.payload().meetingId());
        assertEquals(roomName, command.payload().roomName());
        assertTrue(command.payload().generateSummary());
        assertTrue(command.payload().generateNodes());

        FakePythonResult fakeResult = createAndUploadSnapshot(command);
        sendSummaryResult(command);
        sendGraphResult(command, fakeResult);
        deleteMessage(COMMAND_QUEUE_URL, received.receiptHandle());

        waitForJavaConsumer(Duration.ofSeconds(45));

        Meeting processedMeeting = meetingRepository.findById(meeting.getId()).orElseThrow();
        assertEquals(AnalysisTaskStatus.SUCCEEDED, processedMeeting.getSummaryStatus());
        assertEquals(AnalysisTaskStatus.SUCCEEDED, processedMeeting.getNodeStatus());
        assertEquals(2, inboxRepository.count());
        assertTrue(summaryRepository.findByMeetingId(meeting.getId()).isPresent());
        assertEquals(3, nodeRepository.countByProjectId(project.getId()));
        assertEquals(3, evidenceRepository.count());
        assertEquals(
                1L,
                graphSyncRepository.findById(project.getId()).orElseThrow().getCurrentGraphVersion()
        );

        var tree = graphQueryService.getTree(project.getId(), memberId);
        assertEquals(1L, tree.graphVersion());
        assertNotNull(tree.root());
    }

    private FakePythonResult createAndUploadSnapshot(MeetingAnalysisRequestedCommand command) throws Exception {
        Instant now = Instant.now();
        String decisionId = UUID.randomUUID().toString();
        String actionId = UUID.randomUUID().toString();
        String issueId = UUID.randomUUID().toString();

        ProjectGraphSnapshot snapshot = new ProjectGraphSnapshot(
                1,
                command.projectId(),
                command.payload().meetingId(),
                command.commandId().toString(),
                1,
                now,
                List.of(
                        new ProjectGraphSnapshotNode(
                                decisionId, command.payload().meetingId(), null, null,
                                GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE,
                                "SQS 기반 비동기 분석 파이프라인 적용",
                                "Java와 Python 사이의 분석 요청과 결과 전달에 SQS를 사용한다.",
                                GraphLinkSource.AI, 1, now, now
                        ),
                        new ProjectGraphSnapshotNode(
                                actionId, command.payload().meetingId(), decisionId, null,
                                GraphNodeType.ACTION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE,
                                "Result Consumer 연결 검증",
                                "S3 Snapshot과 Result SQS 이벤트를 이용해 Java Projection 갱신을 검증한다.",
                                GraphLinkSource.AI, 1, now, now
                        ),
                        new ProjectGraphSnapshotNode(
                                issueId, command.payload().meetingId(), actionId, null,
                                GraphNodeType.ISSUE, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE,
                                "운영 전 DLQ와 재시도 정책 확인",
                                "실패 메시지가 Result DLQ로 이동하는지 운영 설정을 확인한다.",
                                GraphLinkSource.AI, 1, now, now
                        )
                ),
                List.of(
                        evidence(command, decisionId, 1, "분석 요청과 결과는 SQS로 비동기 처리합니다."),
                        evidence(command, actionId, 1, "노드 Snapshot은 S3에 올리고 Java가 내려받습니다."),
                        evidence(command, issueId, 1, "실패 메시지는 DLQ에서 확인합니다.")
                ),
                List.of()
        );

        byte[] body = objectMapper.writeValueAsBytes(snapshot);
        String sha256 = HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(body));
        snapshotObjectKey = SNAPSHOT_PREFIX + "aws-e2e/" + command.commandId() + "/v1.json";

        graphSnapshotS3Client.putObject(
                PutObjectRequest.builder()
                        .bucket(SNAPSHOT_BUCKET)
                        .key(snapshotObjectKey)
                        .contentType("application/json")
                        .contentLength((long) body.length)
                        .metadata(Map.of("test-type", "meeting-analysis-aws-e2e"))
                        .build(),
                RequestBody.fromBytes(body)
        );
        return new FakePythonResult(body.length, sha256);
    }

    private ProjectGraphSnapshotEvidence evidence(
            MeetingAnalysisRequestedCommand command,
            String nodeId,
            int order,
            String quote
    ) {
        return new ProjectGraphSnapshotEvidence(
                UUID.randomUUID().toString(),
                nodeId,
                command.payload().meetingId(),
                quote,
                "aws-smoke",
                null,
                null,
                order
        );
    }

    private void sendSummaryResult(MeetingAnalysisRequestedCommand command) throws Exception {
        summaryEventId = UUID.randomUUID().toString();
        ObjectNode payload = objectMapper.createObjectNode()
                .put("meetingSummaryId", UUID.randomUUID().toString())
                .put("summaryVersion", 1)
                .put("status", "READY")
                .put("apiPath", "/api/v1/meetings/" + command.payload().meetingId()
                        + "/summary?summaryVersion=1");
        sendResultEvent(summaryEventId, "MEETING_SUMMARY_READY", command, payload);
    }

    private void sendGraphResult(MeetingAnalysisRequestedCommand command, FakePythonResult result) throws Exception {
        graphEventId = UUID.randomUUID().toString();
        ObjectNode snapshotRef = objectMapper.createObjectNode()
                .put("bucket", SNAPSHOT_BUCKET)
                .put("objectKey", snapshotObjectKey)
                .put("contentType", "application/json")
                .put("sizeBytes", result.sizeBytes())
                .put("sha256", result.sha256());
        ObjectNode payload = objectMapper.createObjectNode()
                .put("sourceType", "MEETING_ANALYSIS")
                .put("graphVersion", 1)
                .set("snapshotRef", snapshotRef);
        sendResultEvent(graphEventId, "PROJECT_GRAPH_CHANGED", command, payload);
    }

    private void sendResultEvent(
            String eventId,
            String eventType,
            MeetingAnalysisRequestedCommand command,
            JsonNode payload
    ) throws Exception {
        ObjectNode event = objectMapper.createObjectNode()
                .put("eventSchemaVersion", 3)
                .put("eventId", eventId)
                .put("eventType", eventType)
                .put("occurredAt", Instant.now().toString())
                .put("projectId", command.projectId())
                .put("meetingId", command.payload().meetingId())
                .put("commandId", command.commandId().toString())
                .set("payload", payload);
        meetingAnalysisSqsClient.sendMessage(SendMessageRequest.builder()
                .queueUrl(RESULT_QUEUE_URL)
                .messageBody(objectMapper.writeValueAsString(event))
                .build());
    }

    private ReceivedCommand receiveTargetCommand(Duration timeout) throws Exception {
        Instant deadline = Instant.now().plus(timeout);
        while (Instant.now().isBefore(deadline)) {
            var messages = meetingAnalysisSqsClient.receiveMessage(ReceiveMessageRequest.builder()
                    .queueUrl(COMMAND_QUEUE_URL)
                    .waitTimeSeconds(1)
                    .maxNumberOfMessages(1)
                    .messageAttributeNames("All")
                    .build()).messages();
            if (messages.isEmpty()) {
                continue;
            }
            var message = messages.getFirst();
            JsonNode body = objectMapper.readTree(message.body());
            if (testCommandId.equals(body.path("commandId").asText())) {
                return new ReceivedCommand(message.body(), message.receiptHandle());
            }
            // Never steal an unrelated command from another worker.
            meetingAnalysisSqsClient.changeMessageVisibility(ChangeMessageVisibilityRequest.builder()
                    .queueUrl(COMMAND_QUEUE_URL)
                    .receiptHandle(message.receiptHandle())
                    .visibilityTimeout(0)
                    .build());
        }
        fail("Timed out waiting for the Java command. Stop any real Python worker and verify Command Queue permissions.");
        throw new IllegalStateException("unreachable");
    }

    private void waitForJavaConsumer(Duration timeout) {
        Instant deadline = Instant.now().plus(timeout);
        while (Instant.now().isBefore(deadline) && inboxRepository.count() < 2) {
            resultConsumer.consumeAvailable();
        }
        assertEquals(
                2,
                inboxRepository.count(),
                "Java must consume both summary and graph result events"
        );
    }

    private void assertQueueEmpty(String queueUrl, String label) {
        Map<QueueAttributeName, String> attributes = meetingAnalysisSqsClient.getQueueAttributes(
                GetQueueAttributesRequest.builder()
                        .queueUrl(queueUrl)
                        .attributeNames(
                                QueueAttributeName.APPROXIMATE_NUMBER_OF_MESSAGES,
                                QueueAttributeName.APPROXIMATE_NUMBER_OF_MESSAGES_NOT_VISIBLE,
                                QueueAttributeName.APPROXIMATE_NUMBER_OF_MESSAGES_DELAYED
                        )
                        .build()
        ).attributes();
        long visible = Long.parseLong(attributes.getOrDefault(
                QueueAttributeName.APPROXIMATE_NUMBER_OF_MESSAGES, "0"));
        long inFlight = Long.parseLong(attributes.getOrDefault(
                QueueAttributeName.APPROXIMATE_NUMBER_OF_MESSAGES_NOT_VISIBLE, "0"));
        long delayed = Long.parseLong(attributes.getOrDefault(
                QueueAttributeName.APPROXIMATE_NUMBER_OF_MESSAGES_DELAYED, "0"));
        assertEquals(
                0,
                visible + inFlight + delayed,
                label + " Queue must be empty and exclusively available for this smoke test"
        );
    }

    private void deleteMatchingMessages(String queueUrl) {
        if (testCommandId == null && summaryEventId == null && graphEventId == null) {
            return;
        }
        for (int attempt = 0; attempt < 5; attempt++) {
            var messages = meetingAnalysisSqsClient.receiveMessage(ReceiveMessageRequest.builder()
                    .queueUrl(queueUrl)
                    .waitTimeSeconds(0)
                    .maxNumberOfMessages(10)
                    .build()).messages();
            if (messages.isEmpty()) {
                return;
            }
            for (var message : messages) {
                if (isOwnedTestMessage(message.body())) {
                    deleteMessage(queueUrl, message.receiptHandle());
                } else {
                    meetingAnalysisSqsClient.changeMessageVisibility(ChangeMessageVisibilityRequest.builder()
                            .queueUrl(queueUrl)
                            .receiptHandle(message.receiptHandle())
                            .visibilityTimeout(0)
                            .build());
                }
            }
        }
    }

    private boolean isOwnedTestMessage(String body) {
        return contains(body, testCommandId) || contains(body, summaryEventId) || contains(body, graphEventId);
    }

    private boolean contains(String body, String value) {
        return value != null && body != null && body.contains(value);
    }

    private void deleteMessage(String queueUrl, String receiptHandle) {
        meetingAnalysisSqsClient.deleteMessage(DeleteMessageRequest.builder()
                .queueUrl(queueUrl)
                .receiptHandle(receiptHandle)
                .build());
    }

    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(name + " must be exported before running the AWS smoke test");
        }
        if (value.contains("{") || value.contains("}")) {
            throw new IllegalStateException(name + " contains an invalid placeholder or malformed URL");
        }
        return value.trim();
    }

    private static String envOrDefault(String name, String defaultValue) {
        String value = System.getenv(name);
        return value == null || value.isBlank() ? defaultValue : value.trim();
    }

    private static String normalizedPrefix(String prefix) {
        String value = prefix.trim();
        return value.endsWith("/") ? value : value + "/";
    }

    private record ReceivedCommand(String body, String receiptHandle) {
    }

    private record FakePythonResult(long sizeBytes, String sha256) {
    }
}
