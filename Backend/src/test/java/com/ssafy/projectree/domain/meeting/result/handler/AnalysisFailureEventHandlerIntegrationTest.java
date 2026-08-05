package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.notification.entity.MeetingAnalysisNotificationOutbox;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationAudience;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationType;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.exception.InvalidAnalysisTaskStateException;
import com.ssafy.projectree.domain.meeting.result.failure.AnalysisTaskType;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultEventProcessor;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultProcessingOutcome;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@SpringBootTest
class AnalysisFailureEventHandlerIntegrationTest {

    @Autowired
    private AnalysisResultEventProcessor processor;
    @Autowired
    private AnalysisFailureEventHandler handler;
    @Autowired
    private MeetingRepository meetingRepository;
    @Autowired
    private MeetingAnalysisCommandOutboxRepository commandRepository;
    @Autowired
    private MeetingAnalysisNotificationOutboxRepository notificationRepository;
    @Autowired
    private MeetingAnalysisResultInboxRepository inboxRepository;
    @Autowired
    private ProjectRepository projectRepository;
    @Autowired
    private ObjectMapper objectMapper;

    @AfterEach
    void cleanUp() {
        inboxRepository.deleteAll();
        notificationRepository.deleteAll();
        commandRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void summaryFailureAtomicallyUpdatesOnlySummaryAndCreatesRequesterNotification() throws Exception {
        Fixture fixture = fixture(true, true);

        assertThat(processor.process(event(fixture, AnalysisTaskType.SUMMARY)))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);

        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        List<MeetingAnalysisNotificationOutbox> notifications = notificationRepository.findAll();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.FAILED);
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(inboxRepository.count()).isEqualTo(1);
        assertThat(notifications).hasSize(1);
        MeetingAnalysisNotificationOutbox notification = notifications.get(0);
        assertThat(notification.getRecipientMemberId()).isEqualTo(17);
        assertThat(notification.getAudience()).isEqualTo(NotificationAudience.USER);
        assertThat(notification.getNotificationType())
                .isEqualTo(NotificationType.MEETING_SUMMARY_ANALYSIS_FAILED);
        JsonNode payload = objectMapper.readTree(notification.getPayload());
        assertThat(payload.get("taskType").asText()).isEqualTo("SUMMARY");
        assertThat(payload.get("failureCode").asText()).isEqualTo("GRAPH_ANALYSIS_FAILED");
        assertThat(payload.get("roomName").asText()).isEqualTo(fixture.roomName());
    }

    @Test
    void nodesFailureOnlyChangesNodes() {
        Fixture fixture = fixture(true, true);

        processor.process(event(fixture, AnalysisTaskType.NODES));

        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.FAILED);
        assertThat(notificationRepository.findAll()).singleElement().satisfies(notification ->
                assertThat(notification.getNotificationType())
                        .isEqualTo(NotificationType.MEETING_NODE_ANALYSIS_FAILED)
        );
    }

    @Test
    void duplicateAndStaleFailureEventsAreDistinguished() {
        Fixture fixture = fixture(true, false);
        AnalysisResultEventEnvelope first = event(fixture, AnalysisTaskType.SUMMARY);

        assertThat(processor.process(first)).isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);
        assertThat(processor.process(first)).isEqualTo(AnalysisResultProcessingOutcome.DUPLICATE);
        assertThat(processor.process(event(fixture, AnalysisTaskType.SUMMARY)))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);

        assertThat(inboxRepository.count()).isEqualTo(2);
        assertThat(notificationRepository.count()).isEqualTo(1);
        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getSummaryStatus())
                .isEqualTo(AnalysisTaskStatus.FAILED);
    }

    @Test
    void staleFailureAfterSuccessKeepsSuccessButRegistersInbox() {
        Fixture fixture = fixture(true, false);
        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        meeting.markSummarySucceeded();
        meetingRepository.saveAndFlush(meeting);

        assertThat(processor.process(event(fixture, AnalysisTaskType.SUMMARY)))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);

        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getSummaryStatus())
                .isEqualTo(AnalysisTaskStatus.SUCCEEDED);
        assertThat(inboxRepository.count()).isEqualTo(1);
        assertThat(notificationRepository.count()).isZero();
    }

    @Test
    void invalidTaskStateAndNotificationFailureRollbackTheEntireHandlerTransaction() {
        Fixture skippedFixture = fixture(false, false);
        assertThatThrownBy(() -> processor.process(event(skippedFixture, AnalysisTaskType.SUMMARY)))
                .isInstanceOf(InvalidAnalysisTaskStateException.class);
        assertThat(inboxRepository.count()).isZero();
        assertThat(notificationRepository.count()).isZero();

        Fixture fixture = fixture(true, false);
        notificationRepository.saveAndFlush(MeetingAnalysisNotificationOutbox.pending(
                fixture.commandId(), fixture.meetingId(), fixture.projectId(), 17,
                NotificationAudience.USER, NotificationType.MEETING_SUMMARY_ANALYSIS_FAILED,
                "{\"existing\":true}"
        ));
        assertThatThrownBy(() -> processor.process(event(fixture, AnalysisTaskType.SUMMARY)))
                .isInstanceOf(org.springframework.dao.DataIntegrityViolationException.class);
        assertThat(inboxRepository.count()).isZero();
        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getSummaryStatus())
                .isEqualTo(AnalysisTaskStatus.PROCESSING);
    }

    @Test
    void handlerRevalidatesMeetingAndCommandInsideTransactionalProxy() {
        Fixture fixture = fixture(true, false);
        AnalysisResultEventEnvelope wrongProject = new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.ANALYSIS_TASK_STATUS_CHANGED,
                Instant.now(), fixture.projectId() + 1, fixture.meetingId(), fixture.commandId(),
                failurePayload(AnalysisTaskType.SUMMARY)
        );

        assertThat(AopUtils.isAopProxy(handler)).isTrue();
        assertThatThrownBy(() -> processor.process(wrongProject))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThat(inboxRepository.count()).isZero();
        assertThat(notificationRepository.count()).isZero();
    }

    private Fixture fixture(boolean generateSummary, boolean generateNodes) {
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(17, ProjectRole.OWNER);
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);

        String roomName = UUID.randomUUID().toString();
        Meeting meeting = Meeting.create(project, creator, roomName);
        meeting.confirmAnalysisOptions(generateSummary, generateNodes);
        meeting = meetingRepository.saveAndFlush(meeting);

        MeetingAnalysisCommandOutbox command = commandRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pending(
                        UUID.randomUUID(), meeting,
                        MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                        "{\"command\":true}", 17, LocalDateTime.now()
                )
        );
        return new Fixture(project.getId(), meeting.getId(), command.getCommandId(), roomName);
    }

    private AnalysisResultEventEnvelope event(Fixture fixture, AnalysisTaskType taskType) {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.ANALYSIS_TASK_STATUS_CHANGED,
                Instant.parse("2026-08-04T12:32:00Z"), fixture.projectId(), fixture.meetingId(),
                fixture.commandId(), failurePayload(taskType)
        );
    }

    private JsonNode failurePayload(AnalysisTaskType taskType) {
        return objectMapper.createObjectNode()
                .put("taskType", taskType.name())
                .put("status", "FAILED")
                .put("failureCode", "GRAPH_ANALYSIS_FAILED")
                .put("failureMessage", "Node analysis failed after maximum retry attempts.");
    }

    private record Fixture(int projectId, int meetingId, String commandId, String roomName) {
    }
}
