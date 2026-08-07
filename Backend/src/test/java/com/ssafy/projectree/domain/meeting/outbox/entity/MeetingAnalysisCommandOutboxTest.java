package com.ssafy.projectree.domain.meeting.outbox.entity;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingAnalysisCommandOutboxTest {

    private static final LocalDateTime NOW = LocalDateTime.of(2026, 8, 4, 10, 0);

    @Test
    void pendingStoresRequesterAndInitialSchedule() {
        MeetingAnalysisCommandOutbox outbox = pending();

        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PENDING);
        assertThat(outbox.getAttemptCount()).isZero();
        assertThat(outbox.getRequestedByMemberId()).isEqualTo(17);
        assertThat(outbox.getNextAttemptAt()).isEqualTo(NOW);
        assertThat(outbox.getLeaseUntil()).isNull();
        assertThat(outbox.getClaimToken()).isNull();
    }

    @Test
    void nodeContentUpdateIsMeetingIndependentAndUsesSameLifecycle() {
        String nodeId = UUID.randomUUID().toString();
        MeetingAnalysisCommandOutbox outbox =
                MeetingAnalysisCommandOutbox.pendingNodeContentUpdate(
                        UUID.randomUUID(),
                        9,
                        nodeId,
                        MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                        "{\"commandType\":\"NODE_CONTENT_UPDATE_REQUESTED\"}",
                        17,
                        NOW
                );

        assertThat(outbox.getMeeting()).isNull();
        assertThat(outbox.getTargetProjectId()).isEqualTo(9);
        assertThat(outbox.getTargetNodeId()).isEqualTo(nodeId);
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PENDING);

        String token = outbox.claim(NOW, NOW.plusSeconds(60), 3);
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHING);
        assertThat(outbox.markPublished(token, NOW.plusSeconds(1))).isTrue();
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHED);
    }

    @Test
    void meetingFactoryRejectsNodeContentUpdateCommandType() {
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(17, ProjectRole.OWNER);
        project.addMember(creator);
        Meeting meeting = Meeting.create(
                project,
                creator,
                "c6db7ac7-d3c7-4f18-928c-ce376ccfabba"
        );

        assertThatThrownBy(() -> MeetingAnalysisCommandOutbox.pending(
                UUID.randomUUID(),
                meeting,
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                "{\"invalid\":true}",
                17,
                NOW
        )).isInstanceOf(IllegalArgumentException.class)
                .hasMessage("commandType must be MEETING_ANALYSIS_REQUESTED");
    }

    @Test
    void nodeUpdateFactoryRejectsMeetingAnalysisCommandType() {
        assertThatThrownBy(() -> MeetingAnalysisCommandOutbox.pendingNodeContentUpdate(
                UUID.randomUUID(),
                1,
                UUID.randomUUID().toString(),
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                "{\"invalid\":true}",
                17,
                NOW
        )).isInstanceOf(IllegalArgumentException.class)
                .hasMessage("commandType must be NODE_CONTENT_UPDATE_REQUESTED");
    }

    @Test
    void normalClaimIncrementsAttemptAndSuccessClearsLease() {
        MeetingAnalysisCommandOutbox outbox = pending();

        String token = outbox.claim(NOW, NOW.plusSeconds(60), 3);

        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHING);
        assertThat(outbox.getAttemptCount()).isEqualTo(1);
        assertThat(outbox.getClaimToken()).isEqualTo(token);
        assertThat(outbox.getLeaseUntil()).isEqualTo(NOW.plusSeconds(60));
        assertThat(outbox.markPublished(token, NOW.plusSeconds(1))).isTrue();
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHED);
        assertThat(outbox.getPublishedAt()).isEqualTo(NOW.plusSeconds(1));
        assertThat(outbox.getClaimToken()).isNull();
        assertThat(outbox.getLeaseUntil()).isNull();
    }

    @Test
    void expiredLeaseRecoveryKeepsAttemptAndReplacesToken() {
        MeetingAnalysisCommandOutbox outbox = pending();
        String oldToken = outbox.claim(NOW, NOW.plusSeconds(60), 3);

        String newToken = outbox.claim(
                NOW.plusSeconds(61),
                NOW.plusSeconds(121),
                3
        );

        assertThat(newToken).isNotEqualTo(oldToken);
        assertThat(outbox.getAttemptCount()).isEqualTo(1);
        assertThat(outbox.markPublished(oldToken, NOW.plusSeconds(62))).isFalse();
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PUBLISHING);
    }

    @Test
    void failuresUseThirtyAndOneHundredTwentySecondRetriesThenFail() {
        MeetingAnalysisCommandOutbox outbox = pending();

        String firstToken = outbox.claim(NOW, NOW.plusSeconds(60), 3);
        assertThat(outbox.rescheduleOrFail(firstToken, NOW, 3, 30, 120, "first"))
                .isFalse();
        assertThat(outbox.getNextAttemptAt()).isEqualTo(NOW.plusSeconds(30));

        String secondToken = outbox.claim(
                NOW.plusSeconds(30),
                NOW.plusSeconds(90),
                3
        );
        assertThat(outbox.rescheduleOrFail(
                secondToken, NOW.plusSeconds(30), 3, 30, 120, "second"
        )).isFalse();
        assertThat(outbox.getNextAttemptAt()).isEqualTo(NOW.plusSeconds(150));

        String thirdToken = outbox.claim(
                NOW.plusSeconds(150),
                NOW.plusSeconds(210),
                3
        );
        assertThat(outbox.rescheduleOrFail(
                thirdToken, NOW.plusSeconds(150), 3, 30, 120, "x".repeat(1100)
        )).isTrue();
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.FAILED);
        assertThat(outbox.getAttemptCount()).isEqualTo(3);
        assertThat(outbox.getLastError()).hasSize(1000);
        assertThat(outbox.getClaimToken()).isNull();
        assertThat(outbox.getLeaseUntil()).isNull();
        assertThat(outbox.getNextAttemptAt()).isNull();
    }

    private MeetingAnalysisCommandOutbox pending() {
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(17, ProjectRole.OWNER);
        project.addMember(creator);
        Meeting meeting = Meeting.create(
                project,
                creator,
                "c6db7ac7-d3c7-4f18-928c-ce376ccfabba"
        );
        return MeetingAnalysisCommandOutbox.pending(
                UUID.randomUUID(),
                meeting,
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                "{\"original\":true}",
                17,
                NOW
        );
    }
}
