package com.ssafy.projectree.domain.meeting.outbox.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.config.MeetingAnalysisPublisherProperties;
import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

class CommandPublishFailureHandlerRetryTest {

    private static final LocalDateTime NOW = LocalDateTime.of(2026, 8, 4, 1, 0);
    private static final String QUEUE_URL =
            "https://sqs.ap-northeast-2.amazonaws.com/000000000000/private";

    @Test
    void firstAndSecondFailuresUseConfiguredDelaysAndSanitizeError() {
        MeetingAnalysisCommandOutboxRepository outboxRepository =
                mock(MeetingAnalysisCommandOutboxRepository.class);
        CommandPublishFailureHandler handler = handler(
                outboxRepository,
                Instant.parse("2026-08-04T01:00:00Z")
        );
        MeetingAnalysisCommandOutbox outbox = pending();
        ReflectionTestUtils.setField(outbox, "id", 31);

        String firstToken = outbox.claim(NOW, NOW.plusSeconds(60), 3);
        ClaimedCommandOutbox first = claimed(outbox, firstToken, 1);
        when(outboxRepository.findOwnedPublishingForUpdate(31, firstToken))
                .thenReturn(Optional.of(outbox));

        assertThat(handler.handle(
                first,
                new IllegalStateException(
                        "failed at " + QUEUE_URL + " body=" + outbox.getPayload()
                )
        )).isEqualTo(CommandPublishFailureOutcome.RETRY_SCHEDULED);
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PENDING);
        assertThat(outbox.getNextAttemptAt()).isEqualTo(NOW.plusSeconds(30));
        assertThat(outbox.getLastError()).doesNotContain(QUEUE_URL);
        assertThat(outbox.getLastError()).doesNotContain(outbox.getPayload());

        String secondToken = outbox.claim(
                NOW.plusSeconds(30),
                NOW.plusSeconds(90),
                3
        );
        ClaimedCommandOutbox second = claimed(outbox, secondToken, 2);
        when(outboxRepository.findOwnedPublishingForUpdate(31, secondToken))
                .thenReturn(Optional.of(outbox));
        handler = handler(
                outboxRepository,
                Instant.parse("2026-08-04T01:00:30Z")
        );

        assertThat(handler.handle(
                second,
                new IllegalStateException("second failure")
        )).isEqualTo(CommandPublishFailureOutcome.RETRY_SCHEDULED);
        assertThat(outbox.getNextAttemptAt()).isEqualTo(NOW.plusSeconds(150));
    }

    @Test
    void finalNodeUpdateFailureDoesNotTouchMeetingOrNotification() {
        MeetingAnalysisCommandOutboxRepository outboxRepository =
                mock(MeetingAnalysisCommandOutboxRepository.class);
        MeetingRepository meetingRepository = mock(MeetingRepository.class);
        MeetingAnalysisNotificationOutboxRepository notificationRepository =
                mock(MeetingAnalysisNotificationOutboxRepository.class);
        CommandPublishFailureHandler handler = new CommandPublishFailureHandler(
                outboxRepository,
                meetingRepository,
                notificationRepository,
                properties(),
                mock(ObjectMapper.class),
                Clock.fixed(Instant.parse("2026-08-04T01:00:00Z"), ZoneOffset.UTC)
        );
        MeetingAnalysisCommandOutbox outbox =
                MeetingAnalysisCommandOutbox.pendingNodeContentUpdate(
                        UUID.randomUUID(),
                        1,
                        UUID.randomUUID().toString(),
                        MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                        "{\"stored\":true}",
                        17,
                        NOW
                );
        ReflectionTestUtils.setField(outbox, "id", 32);
        ReflectionTestUtils.setField(outbox, "attemptCount", 2);
        String token = outbox.claim(NOW, NOW.plusSeconds(60), 3);
        when(outboxRepository.findOwnedPublishingForUpdate(32, token))
                .thenReturn(Optional.of(outbox));

        assertThat(handler.handle(claimed(outbox, token, 3), new IllegalStateException("failed")))
                .isEqualTo(CommandPublishFailureOutcome.FINAL_FAILED);
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.FAILED);
        verifyNoInteractions(meetingRepository, notificationRepository);
    }

    private ClaimedCommandOutbox claimed(
            MeetingAnalysisCommandOutbox outbox,
            String token,
            int attemptCount
    ) {
        return new ClaimedCommandOutbox(
                outbox.getId(),
                outbox.getCommandId(),
                outbox.getPayload(),
                token,
                attemptCount
        );
    }

    private MeetingAnalysisCommandOutbox pending() {
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(17, ProjectRole.OWNER);
        project.addMember(creator);
        Meeting meeting = Meeting.create(project, creator, UUID.randomUUID().toString());
        return MeetingAnalysisCommandOutbox.pending(
                UUID.randomUUID(),
                meeting,
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                "{\"stored\":true}",
                17,
                NOW
        );
    }

    private MeetingAnalysisPublisherProperties properties() {
        return new MeetingAnalysisPublisherProperties(
                false, 1000, 20, 3, 60, 30, 120, 5, 10,
                QUEUE_URL,
                "ap-northeast-2"
        );
    }

    private CommandPublishFailureHandler handler(
            MeetingAnalysisCommandOutboxRepository outboxRepository,
            Instant now
    ) {
        return new CommandPublishFailureHandler(
                outboxRepository,
                mock(MeetingRepository.class),
                mock(MeetingAnalysisNotificationOutboxRepository.class),
                properties(),
                mock(ObjectMapper.class),
                Clock.fixed(now, ZoneOffset.UTC)
        );
    }
}
