package com.ssafy.projectree.domain.meeting.outbox.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class CommandPublishSuccessHandlerTest {

    private static final Instant NOW = Instant.parse("2026-08-04T01:00:00Z");

    @Test
    void currentTokenMarksPublishedAndStaleTokenIsNoOp() {
        MeetingAnalysisCommandOutboxRepository repository =
                mock(MeetingAnalysisCommandOutboxRepository.class);
        CommandPublishSuccessHandler handler = new CommandPublishSuccessHandler(
                repository,
                Clock.fixed(NOW, ZoneOffset.UTC)
        );
        MeetingAnalysisCommandOutbox outbox = pending();
        String token = outbox.claim(
                LocalDateTime.ofInstant(NOW, ZoneOffset.UTC),
                LocalDateTime.ofInstant(NOW.plusSeconds(60), ZoneOffset.UTC),
                3
        );
        ReflectionTestUtils.setField(outbox, "id", 11);
        ClaimedCommandOutbox current =
                new ClaimedCommandOutbox(11, outbox.getCommandId(), outbox.getPayload(), token, 1);
        when(repository.findOwnedPublishingForUpdate(11, token))
                .thenReturn(Optional.of(outbox));

        assertThat(handler.handle(current)).isTrue();
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHED);
        assertThat(outbox.getPublishedAt())
                .isEqualTo(LocalDateTime.ofInstant(NOW, ZoneOffset.UTC));

        ClaimedCommandOutbox stale =
                new ClaimedCommandOutbox(11, outbox.getCommandId(), outbox.getPayload(), "old", 1);
        when(repository.findOwnedPublishingForUpdate(11, "old")).thenReturn(Optional.empty());
        assertThat(handler.handle(stale)).isFalse();
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHED);
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
                LocalDateTime.ofInstant(NOW, ZoneOffset.UTC)
        );
    }
}
