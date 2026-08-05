package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import org.junit.jupiter.api.Test;

import java.time.Instant;

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
}
