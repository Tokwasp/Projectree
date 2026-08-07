package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProjectGraphSyncTest {

    @Test
    void initializesAtVersionZeroAndAdvancesOnlyToNewerVersion() {
        Instant initialAt = Instant.parse("2026-08-05T00:00:00Z");
        ProjectGraphSync sync = ProjectGraphSync.initial(7, initialAt);

        assertThat(sync.getProjectId()).isEqualTo(7);
        assertThat(sync.getCurrentGraphVersion()).isZero();
        assertThat(sync.getLastCommandId()).isNull();
        assertThat(sync.getSyncedAt()).isEqualTo(initialAt);

        Instant advancedAt = initialAt.plusSeconds(1);
        sync.advanceTo(3, "6c4fa638-b34f-4d7a-91ae-9ca8b43f772a", advancedAt);

        assertThat(sync.getCurrentGraphVersion()).isEqualTo(3);
        assertThat(sync.getLastCommandId()).isEqualTo("6c4fa638-b34f-4d7a-91ae-9ca8b43f772a");
        assertThat(sync.getSyncedAt()).isEqualTo(advancedAt);
        assertThatThrownBy(() -> sync.advanceTo(3, "another", advancedAt))
                .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> sync.advanceTo(2, "another", advancedAt))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void acquiresAndReleasesAllGuardFieldsTogether() {
        ProjectGraphSync sync = ProjectGraphSync.initial(7, Instant.EPOCH);
        String commandId = UUID.randomUUID().toString();
        Instant acquiredAt = Instant.parse("2026-08-07T01:00:00Z");

        assertThat(sync.hasActiveCommand()).isFalse();

        sync.acquireGraphOperation(
                commandId,
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                acquiredAt
        );

        assertThat(sync.hasActiveCommand()).isTrue();
        assertThat(sync.getActiveCommandId()).isEqualTo(commandId);
        assertThat(sync.getActiveCommandType())
                .isEqualTo(MeetingAnalysisCommandType.NODE_DELETE_REQUESTED);
        assertThat(sync.getActiveSince()).isEqualTo(acquiredAt);

        assertThat(sync.releaseGraphOperation(commandId)).isTrue();
        assertThat(sync.hasActiveCommand()).isFalse();
        assertThat(sync.getActiveCommandId()).isNull();
        assertThat(sync.getActiveCommandType()).isNull();
        assertThat(sync.getActiveSince()).isNull();
    }

    @Test
    void rejectsReacquisitionAndMismatchedReleaseKeepsCurrentGuard() {
        ProjectGraphSync sync = ProjectGraphSync.initial(7, Instant.EPOCH);
        String activeCommandId = UUID.randomUUID().toString();
        sync.acquireGraphOperation(
                activeCommandId,
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                Instant.EPOCH.plusSeconds(1)
        );

        assertThatThrownBy(() -> sync.acquireGraphOperation(
                UUID.randomUUID().toString(),
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                Instant.EPOCH.plusSeconds(2)
        )).isInstanceOf(IllegalStateException.class);

        assertThat(sync.releaseGraphOperation(UUID.randomUUID().toString())).isFalse();
        assertThat(sync.getActiveCommandId()).isEqualTo(activeCommandId);
        assertThat(sync.releaseGraphOperation(null)).isFalse();
    }

    @Test
    void releaseWithoutGuardReturnsFalseAndInvalidAcquireArgumentsAreRejected() {
        ProjectGraphSync sync = ProjectGraphSync.initial(7, Instant.EPOCH);

        assertThat(sync.releaseGraphOperation(UUID.randomUUID().toString())).isFalse();
        assertThatThrownBy(() -> sync.acquireGraphOperation(
                "not-a-uuid",
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                Instant.EPOCH
        )).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> sync.acquireGraphOperation(
                UUID.randomUUID().toString(),
                null,
                Instant.EPOCH
        )).isInstanceOf(NullPointerException.class);
        assertThatThrownBy(() -> sync.acquireGraphOperation(
                UUID.randomUUID().toString(),
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                null
        )).isInstanceOf(NullPointerException.class);
    }

    @Test
    void rejectsIncompleteGuardState() {
        ProjectGraphSync sync = ProjectGraphSync.initial(7, Instant.EPOCH);
        ReflectionTestUtils.setField(
                sync,
                "activeCommandId",
                UUID.randomUUID().toString()
        );

        assertThatThrownBy(sync::hasActiveCommand)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("all present or all null");
    }
}
