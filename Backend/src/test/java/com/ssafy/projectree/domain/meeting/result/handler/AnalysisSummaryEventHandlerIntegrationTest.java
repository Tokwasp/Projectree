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
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultEventProcessor;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultProcessingOutcome;
import com.ssafy.projectree.domain.meeting.result.summary.entity.MeetingSummaryProjection;
import com.ssafy.projectree.domain.meeting.result.summary.repository.MeetingSummaryProjectionRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
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
class AnalysisSummaryEventHandlerIntegrationTest {

    @Autowired private AnalysisResultEventProcessor processor;
    @Autowired private AnalysisSummaryEventHandler handler;
    @Autowired private MeetingRepository meetingRepository;
    @Autowired private MeetingAnalysisCommandOutboxRepository commandRepository;
    @Autowired private MeetingAnalysisNotificationOutboxRepository notificationRepository;
    @Autowired private MeetingAnalysisResultInboxRepository inboxRepository;
    @Autowired private MeetingSummaryProjectionRepository projectionRepository;
    @Autowired private ProjectRepository projectRepository;
    @Autowired private ObjectMapper objectMapper;
    @Autowired private ProjectGraphSyncRepository graphSyncRepository;

    @AfterEach
    void cleanUp() {
        inboxRepository.deleteAll();
        notificationRepository.deleteAll();
        projectionRepository.deleteAll();
        commandRepository.deleteAll();
        meetingRepository.deleteAll();
        graphSyncRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @Test
    void processingSummarySuccessCommitsInboxProjectionStatusAndRequesterNotification() throws Exception {
        Fixture fixture = fixture(true, true);

        assertThat(processor.process(event(fixture, 1, "first")))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);

        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        MeetingSummaryProjection projection = projectionRepository.findByMeetingId(fixture.meetingId()).orElseThrow();
        List<MeetingAnalysisNotificationOutbox> notifications = notificationRepository.findAll();
        assertThat(AopUtils.isAopProxy(handler)).isTrue();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.SUCCEEDED);
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isTrue();
        assertThat(inboxRepository.count()).isEqualTo(1);
        assertThat(projection.getSummaryVersion()).isEqualTo(1);
        assertThat(notifications).hasSize(1);
        MeetingAnalysisNotificationOutbox notification = notifications.get(0);
        assertThat(notification.getRecipientMemberId()).isEqualTo(17);
        assertThat(notification.getNotificationType())
                .isEqualTo(NotificationType.MEETING_SUMMARY_ANALYSIS_SUCCEEDED);
        JsonNode payload = objectMapper.readTree(notification.getPayload());
        assertThat(payload.get("meetingSummaryId").asText()).isEqualTo(summaryId("first"));
        assertThat(payload.get("summaryVersion").asInt()).isEqualTo(1);
        assertThat(payload.get("apiPath").asText())
                .isEqualTo(apiPath(fixture.meetingId(), 1));
    }

    @Test
    void duplicateAndVersionedStaleEventsKeepNotificationSingleAndProjectionLatest() {
        Fixture fixture = fixture(true, false);
        AnalysisResultEventEnvelope first = event(fixture, 1, "first");

        assertThat(processor.process(first)).isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);
        assertThat(processor.process(first)).isEqualTo(AnalysisResultProcessingOutcome.DUPLICATE);
        assertThat(processor.process(event(fixture, 1, "first")))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);
        assertThat(processor.process(event(fixture, 2, "second")))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);
        assertThat(processor.process(event(fixture, 1, "first")))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);

        assertThat(inboxRepository.count()).isEqualTo(4);
        assertThat(notificationRepository.count()).isEqualTo(1);
        assertThat(projectionRepository.findByMeetingId(fixture.meetingId()).orElseThrow()
                .getSummaryVersion()).isEqualTo(2);
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isFalse();
    }

    @Test
    void failedSummaryKeepsFailureAndDoesNotCreateProjectionOrSuccessNotification() {
        Fixture fixture = fixture(true, false);
        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        meeting.markSummaryFailed();
        meetingRepository.saveAndFlush(meeting);

        assertThat(processor.process(event(fixture, 1, "late-success")))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);

        assertThat(meetingRepository.findById(fixture.meetingId()).orElseThrow().getSummaryStatus())
                .isEqualTo(AnalysisTaskStatus.FAILED);
        assertThat(inboxRepository.count()).isEqualTo(1);
        assertThat(projectionRepository.count()).isZero();
        assertThat(notificationRepository.count()).isZero();
    }

    @Test
    void invalidStateAndProjectionOrNotificationFailuresRollbackEntireTransaction() {
        Fixture skipped = fixture(false, false);
        assertThatThrownBy(() -> processor.process(event(skipped, 1, "skipped")))
                .isInstanceOf(InvalidAnalysisTaskStateException.class);
        assertThat(inboxRepository.count()).isZero();
        assertThat(projectionRepository.count()).isZero();

        Fixture conflict = fixture(true, false);
        assertThat(processor.process(event(conflict, 1, "first")))
                .isEqualTo(AnalysisResultProcessingOutcome.PROCESSED);
        assertThatThrownBy(() -> processor.process(event(conflict, 1, "different")))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThat(inboxRepository.count()).isEqualTo(1);

        cleanUp();
        Fixture notificationConflict = fixture(true, false);
        notificationRepository.saveAndFlush(MeetingAnalysisNotificationOutbox.pending(
                notificationConflict.commandId(), notificationConflict.meetingId(), notificationConflict.projectId(),
                17, NotificationAudience.USER, NotificationType.MEETING_SUMMARY_ANALYSIS_SUCCEEDED,
                "{\"existing\":true}"
        ));
        assertThatThrownBy(() -> processor.process(event(notificationConflict, 1, "first")))
                .isInstanceOf(DataIntegrityViolationException.class);
        assertThat(inboxRepository.count()).isZero();
        assertThat(projectionRepository.count()).isZero();
        assertThat(meetingRepository.findById(notificationConflict.meetingId()).orElseThrow().getSummaryStatus())
                .isEqualTo(AnalysisTaskStatus.PROCESSING);
    }

    private Fixture fixture(boolean generateSummary, boolean generateNodes) {
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(17, ProjectRole.OWNER);
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);
        Meeting meeting = Meeting.create(project, creator, UUID.randomUUID().toString());
        meeting.confirmAnalysisOptions(generateSummary, generateNodes);
        meeting = meetingRepository.saveAndFlush(meeting);
        MeetingAnalysisCommandOutbox command = commandRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pending(
                        UUID.randomUUID(), meeting,
                        MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                        "{\"command\":true}", 17, LocalDateTime.now()
                )
        );
        ProjectGraphSync sync = ProjectGraphSync.initial(project.getId(), Instant.EPOCH);
        if (generateNodes) {
            sync.acquireGraphOperation(
                    command.getCommandId(),
                    MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                    Instant.EPOCH.plusSeconds(1)
            );
        }
        graphSyncRepository.saveAndFlush(sync);
        return new Fixture(project.getId(), meeting.getId(), command.getCommandId());
    }

    private AnalysisResultEventEnvelope event(Fixture fixture, int version, String suffix) {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.MEETING_SUMMARY_READY,
                Instant.parse("2026-08-04T12:31:00Z"), fixture.projectId(), fixture.meetingId(),
                fixture.commandId(), payload(fixture.meetingId(), version, suffix)
        );
    }

    private JsonNode payload(int meetingId, int version, String suffix) {
        return objectMapper.createObjectNode()
                .put("meetingSummaryId", summaryId(suffix))
                .put("summaryVersion", version)
                .put("status", "READY")
                .put("apiPath", apiPath(meetingId, version));
    }

    private String summaryId(String suffix) {
        return UUID.nameUUIDFromBytes(suffix.getBytes()).toString();
    }

    private String apiPath(int meetingId, int version) {
        return "/api/v1/meetings/" + meetingId + "/summary?summaryVersion=" + version;
    }

    private record Fixture(int projectId, int meetingId, String commandId) {
    }
}
