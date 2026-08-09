package com.ssafy.projectree.domain.meeting.result.graph.operation;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

class ProjectGraphOperationGuardRepositoryIntegrationTest
        extends IntegrationTestSupport {

    @Autowired
    private ProjectGraphSyncRepository syncRepository;

    @Test
    void findsOnlyRequestedProjectWithPessimisticWriteQuery() {
        ProjectGraphSync first = ProjectGraphSync.initial(101, Instant.EPOCH);
        first.acquireGraphOperation(
                UUID.randomUUID().toString(),
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                Instant.EPOCH.plusSeconds(1)
        );
        ProjectGraphSync second = ProjectGraphSync.initial(102, Instant.EPOCH);
        syncRepository.saveAndFlush(first);
        syncRepository.saveAndFlush(second);

        ProjectGraphSync locked = syncRepository.findByProjectIdForUpdate(101)
                .orElseThrow();

        assertThat(locked.getProjectId()).isEqualTo(101);
        assertThat(locked.hasActiveCommand()).isTrue();
        assertThat(syncRepository.findByProjectIdForUpdate(102))
                .get()
                .matches(sync -> !sync.hasActiveCommand());
        assertThat(syncRepository.findByProjectIdForUpdate(999))
                .isEmpty();
    }
}
