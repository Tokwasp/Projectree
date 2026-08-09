package com.ssafy.projectree.domain.meeting.outbox.service;

import com.ssafy.projectree.ProjectreeApplication;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisRequestedCommand;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.notification.entity.MeetingAnalysisNotificationOutbox;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationAudience;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationOutboxStatus;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.util.ReflectionTestUtils;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneId;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

@ActiveProfiles("test")
@SpringBootTest(classes = {
        ProjectreeApplication.class,
        CommandPublishFailureHandlerIntegrationTest.FixedClockConfig.class
})
class CommandPublishFailureHandlerIntegrationTest {

    private static final LocalDateTime NOW = LocalDateTime.of(2026, 8, 4, 10, 0);

    @Autowired
    private CommandPublishFailureHandler failureHandler;
    @Autowired
    private CommandOutboxClaimService claimService;
    @Autowired
    private MeetingAnalysisCommandOutboxRepository outboxRepository;
    @Autowired
    private MeetingAnalysisNotificationOutboxRepository notificationRepository;
    @Autowired
    private MeetingRepository meetingRepository;
    @Autowired
    private ProjectRepository projectRepository;
    @Autowired
    private ProjectGraphSyncRepository graphSyncRepository;
    @Autowired
    private ObjectMapper objectMapper;
    @MockitoSpyBean
    private ProjectGraphOperationGuard graphOperationGuard;

    @AfterEach
    void cleanUp() {
        notificationRepository.deleteAll();
        outboxRepository.deleteAll();
        meetingRepository.deleteAll();
        graphSyncRepository.deleteAll();
        projectRepository.deleteAll();
    }

    @ParameterizedTest
    @CsvSource({
            "true,false,FAILED,SKIPPED,2",
            "false,true,SKIPPED,FAILED,2",
            "true,true,FAILED,FAILED,2",
            "false,false,SKIPPED,SKIPPED,1"
    })
    void finalFailureUpdatesOnlySelectedTasksAndCreatesNotifications(
            boolean generateSummary,
            boolean generateNodes,
            AnalysisTaskStatus expectedSummary,
            AnalysisTaskStatus expectedNodes,
            int expectedNotifications
    ) {
        Fixture fixture = fixture(generateSummary, generateNodes);

        CommandPublishFailureOutcome outcome = failureHandler.handle(
                fixture.claimed(),
                new IllegalStateException(
                        "queue failed at https://sqs.example.invalid/private"
                )
        );

        assertThat(outcome).isEqualTo(CommandPublishFailureOutcome.FINAL_FAILED);
        MeetingAnalysisCommandOutbox outbox = outboxRepository
                .findById(fixture.outboxId())
                .orElseThrow();
        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        List<MeetingAnalysisNotificationOutbox> notifications = notificationRepository.findAll();
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.FAILED);
        assertThat(outbox.getClaimToken()).isNull();
        assertThat(outbox.getLeaseUntil()).isNull();
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isFalse();
        assertThat(meeting.getSummaryStatus()).isEqualTo(expectedSummary);
        assertThat(meeting.getNodeStatus()).isEqualTo(expectedNodes);
        assertThat(notifications).hasSize(expectedNotifications);
        assertThat(notifications).allMatch(
                notification -> notification.getStatus() == NotificationOutboxStatus.PENDING
        );
        assertThat(notifications).anyMatch(
                notification -> notification.getAudience() == NotificationAudience.OPERATIONS
        );
        if (generateSummary || generateNodes) {
            assertThat(notifications).anyMatch(
                    notification -> notification.getAudience() == NotificationAudience.USER
                            && notification.getRecipientMemberId() == 17
            );
        } else {
            assertThat(notifications).noneMatch(
                    notification -> notification.getAudience() == NotificationAudience.USER
            );
        }
    }

    @Test
    void staleTokenCannotChangeOutboxMeetingOrNotifications() {
        Fixture fixture = fixture(true, true);
        ClaimedCommandOutbox stale = new ClaimedCommandOutbox(
                fixture.claimed().outboxId(),
                fixture.claimed().commandId(),
                fixture.claimed().payload(),
                "stale-token",
                fixture.claimed().attemptCount()
        );

        CommandPublishFailureOutcome outcome =
                failureHandler.handle(stale, new IllegalStateException("late failure"));

        assertThat(outcome).isEqualTo(CommandPublishFailureOutcome.STALE);
        assertThat(outboxRepository.findById(fixture.outboxId()).orElseThrow().getStatus())
                .isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHING);
        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(notificationRepository.count()).isZero();
    }

    @Test
    void notificationConstraintFailureRollsBackOutboxAndMeetingThenLeaseCanRecover() {
        Fixture fixture = fixture(true, true);
        notificationRepository.saveAndFlush(MeetingAnalysisNotificationOutbox.pending(
                fixture.claimed().commandId(),
                fixture.meetingId(),
                fixture.projectId(),
                17,
                NotificationAudience.USER,
                "{\"existing\":true}"
        ));

        assertThatThrownBy(() -> failureHandler.handle(
                fixture.claimed(),
                new IllegalStateException("final failure")
        )).isInstanceOf(DataIntegrityViolationException.class);

        MeetingAnalysisCommandOutbox rolledBackOutbox =
                outboxRepository.findById(fixture.outboxId()).orElseThrow();
        Meeting rolledBackMeeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        assertThat(rolledBackOutbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHING);
        assertThat(rolledBackOutbox.getClaimToken()).isEqualTo(fixture.claimed().claimToken());
        assertThat(rolledBackMeeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(rolledBackMeeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(notificationRepository.count()).isEqualTo(1);
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isTrue();

        ReflectionTestUtils.setField(rolledBackOutbox, "leaseUntil", NOW.minusSeconds(1));
        outboxRepository.saveAndFlush(rolledBackOutbox);
        List<ClaimedCommandOutbox> reclaimed = claimService.claimAvailable();
        assertThat(reclaimed).hasSize(1);
        assertThat(reclaimed.get(0).attemptCount()).isEqualTo(3);
        assertThat(reclaimed.get(0).claimToken())
                .isNotEqualTo(fixture.claimed().claimToken());
    }

    @Test
    void invalidMeetingCommandPayloadDoesNotReleaseGuardOrCommitFinalFailure() {
        Fixture fixture = fixture(true, true);
        MeetingAnalysisCommandOutbox outbox = outboxRepository
                .findById(fixture.outboxId())
                .orElseThrow();
        ReflectionTestUtils.setField(outbox, "payload", "{\"invalid\":true}");
        outboxRepository.saveAndFlush(outbox);

        assertThatThrownBy(() -> failureHandler.handle(
                fixture.claimed(),
                new IllegalStateException("final failure")
        ))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("payload");

        assertThat(outboxRepository.findById(fixture.outboxId()).orElseThrow().getStatus())
                .isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHING);
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isTrue();
        assertThat(notificationRepository.count()).isZero();
    }

    @ParameterizedTest
    @EnumSource(PayloadMismatch.class)
    void meetingAnalysisFinalFailureRejectsPayloadMismatch(
            PayloadMismatch mismatch
    ) {
        Fixture fixture = fixture(true, true);
        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        MeetingAnalysisCommandOutbox outbox = outboxRepository
                .findById(fixture.outboxId())
                .orElseThrow();
        MeetingAnalysisRequestedCommand original = objectMapper.readValue(
                outbox.getPayload(),
                MeetingAnalysisRequestedCommand.class
        );
        MeetingAnalysisRequestedCommand.Payload payload = switch (mismatch) {
            case ROOM_NAME -> new MeetingAnalysisRequestedCommand.Payload(
                    meeting.getId(),
                    meeting.getRoomName() + "-mismatch",
                    meeting.isGenerateSummary(),
                    meeting.isGenerateNodes()
            );
            case GENERATE_SUMMARY -> new MeetingAnalysisRequestedCommand.Payload(
                    meeting.getId(),
                    meeting.getRoomName(),
                    !meeting.isGenerateSummary(),
                    meeting.isGenerateNodes()
            );
            case GENERATE_NODES -> new MeetingAnalysisRequestedCommand.Payload(
                    meeting.getId(),
                    meeting.getRoomName(),
                    meeting.isGenerateSummary(),
                    !meeting.isGenerateNodes()
            );
        };
        MeetingAnalysisRequestedCommand mismatchedCommand =
                new MeetingAnalysisRequestedCommand(
                        original.commandSchemaVersion(),
                        original.commandId(),
                        original.commandType(),
                        original.requestedAt(),
                        original.projectId(),
                        payload
                );
        ReflectionTestUtils.setField(
                outbox,
                "payload",
                objectMapper.writeValueAsString(mismatchedCommand)
        );
        outboxRepository.saveAndFlush(outbox);

        assertThatThrownBy(() -> failureHandler.handle(
                fixture.claimed(),
                new IllegalStateException("final failure")
        ))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("payload does not match");

        MeetingAnalysisCommandOutbox rolledBackOutbox = outboxRepository
                .findById(fixture.outboxId())
                .orElseThrow();
        Meeting rolledBackMeeting = meetingRepository
                .findById(fixture.meetingId())
                .orElseThrow();
        ProjectGraphSync retainedGuard = graphSyncRepository
                .findById(fixture.projectId())
                .orElseThrow();
        assertThat(rolledBackOutbox.getStatus())
                .isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHING);
        assertThat(rolledBackOutbox.getClaimToken())
                .isEqualTo(fixture.claimed().claimToken());
        assertThat(rolledBackMeeting.getSummaryStatus())
                .isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(rolledBackMeeting.getNodeStatus())
                .isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(retainedGuard.hasActiveCommand()).isTrue();
        assertThat(retainedGuard.getActiveCommandId())
                .isEqualTo(fixture.claimed().commandId());
        assertThat(notificationRepository.count()).isZero();
    }

    @Test
    void summaryOnlyFinalFailureDoesNotAttemptGuardRelease() {
        Fixture fixture = fixture(true, false);
        clearInvocations(graphOperationGuard);

        assertThat(failureHandler.handle(
                fixture.claimed(),
                new IllegalStateException("final failure")
        )).isEqualTo(CommandPublishFailureOutcome.FINAL_FAILED);

        verify(graphOperationGuard, never()).release(
                anyInt(),
                anyString(),
                anyString()
        );
        assertThat(graphSyncRepository.findById(fixture.projectId()).orElseThrow()
                .hasActiveCommand()).isFalse();
    }

    private Fixture fixture(boolean generateSummary, boolean generateNodes) {
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(17, ProjectRole.OWNER);
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);
        Meeting meeting = Meeting.create(project, creator, UUID.randomUUID().toString());
        meeting.confirmAnalysisOptions(generateSummary, generateNodes);
        meeting = meetingRepository.saveAndFlush(meeting);

        UUID commandId = UUID.randomUUID();
        MeetingAnalysisRequestedCommand command =
                new MeetingAnalysisRequestedCommand(
                        MeetingAnalysisRequestedCommand.CURRENT_SCHEMA_VERSION,
                        commandId,
                        MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                        Instant.parse("2026-08-04T00:30:00Z"),
                        project.getId(),
                        new MeetingAnalysisRequestedCommand.Payload(
                                meeting.getId(),
                                meeting.getRoomName(),
                                generateSummary,
                                generateNodes
                        )
                );
        MeetingAnalysisCommandOutbox outbox = MeetingAnalysisCommandOutbox.pending(
                commandId,
                meeting,
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                objectMapper.writeValueAsString(command),
                17,
                NOW.minusSeconds(150)
        );
        String first = outbox.claim(
                NOW.minusSeconds(150),
                NOW.minusSeconds(90),
                3
        );
        outbox.rescheduleOrFail(first, NOW.minusSeconds(150), 3, 30, 120, "first");
        String second = outbox.claim(
                NOW.minusSeconds(120),
                NOW.minusSeconds(60),
                3
        );
        outbox.rescheduleOrFail(second, NOW.minusSeconds(120), 3, 30, 120, "second");
        String third = outbox.claim(NOW, NOW.plusSeconds(60), 3);
        outbox = outboxRepository.saveAndFlush(outbox);
        ProjectGraphSync sync = ProjectGraphSync.initial(
                project.getId(),
                Instant.parse("2026-08-04T00:00:00Z")
        );
        if (generateNodes) {
            sync.acquireGraphOperation(
                    outbox.getCommandId(),
                    MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                    Instant.parse("2026-08-04T00:30:00Z")
            );
        }
        graphSyncRepository.saveAndFlush(sync);
        return new Fixture(
                project.getId(),
                meeting.getId(),
                outbox.getId(),
                new ClaimedCommandOutbox(
                        outbox.getId(),
                        outbox.getCommandId(),
                        outbox.getPayload(),
                        third,
                        3
                )
        );
    }

    private record Fixture(
            int projectId,
            int meetingId,
            int outboxId,
            ClaimedCommandOutbox claimed
    ) {
    }

    private enum PayloadMismatch {
        ROOM_NAME,
        GENERATE_SUMMARY,
        GENERATE_NODES
    }

    @TestConfiguration
    static class FixedClockConfig {
        @Bean
        @Primary
        Clock fixedMeetingAnalysisClock() {
            return Clock.fixed(
                    Instant.parse("2026-08-04T01:00:00Z"),
                    ZoneId.of("Asia/Seoul")
            );
        }
    }
}
