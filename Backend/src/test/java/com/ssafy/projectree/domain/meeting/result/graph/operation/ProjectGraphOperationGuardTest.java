package com.ssafy.projectree.domain.meeting.result.graph.operation;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProjectGraphOperationGuardTest {

    @Mock
    private ProjectGraphSyncRepository syncRepository;

    private ProjectGraphOperationGuard guard;

    @BeforeEach
    void setUp() {
        guard = new ProjectGraphOperationGuard(syncRepository);
    }

    @Test
    void acquiresLockedProjectGuardForEveryGraphCommandType() {
        for (MeetingAnalysisCommandType commandType
                : MeetingAnalysisCommandType.values()) {
            int projectId = commandType.ordinal() + 1;
            ProjectGraphSync sync = ProjectGraphSync.initial(
                    projectId,
                    Instant.EPOCH
            );
            UUID commandId = UUID.randomUUID();
            when(syncRepository.findByProjectIdForUpdate(projectId))
                    .thenReturn(Optional.of(sync));

            assertThat(guard.acquire(
                    projectId,
                    commandId,
                    commandType,
                    Instant.EPOCH.plusSeconds(1)
            )).isSameAs(sync);
            assertThat(sync.getActiveCommandId()).isEqualTo(commandId.toString());
            assertThat(sync.getActiveCommandType()).isEqualTo(commandType);
        }
    }

    @Test
    void rejectsWhenProjectAlreadyHasActiveCommand() {
        ProjectGraphSync sync = ProjectGraphSync.initial(1, Instant.EPOCH);
        sync.acquireGraphOperation(
                UUID.randomUUID().toString(),
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                Instant.EPOCH.plusSeconds(1)
        );
        when(syncRepository.findByProjectIdForUpdate(1))
                .thenReturn(Optional.of(sync));

        assertThatThrownBy(() -> guard.acquire(
                1,
                UUID.randomUUID(),
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                Instant.EPOCH.plusSeconds(2)
        ))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(ProjectGraphOperationErrorCode.GRAPH_OPERATION_IN_PROGRESS);
    }

    @Test
    void missingSyncIsAnInternalStateError() {
        when(syncRepository.findByProjectIdForUpdate(99))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> guard.acquire(
                99,
                UUID.randomUUID(),
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                Instant.EPOCH
        ))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(ProjectGraphOperationErrorCode.PROJECT_GRAPH_SYNC_NOT_FOUND);
    }

    @Test
    void staleReleaseCannotClearNewerCommand() {
        ProjectGraphSync sync = ProjectGraphSync.initial(1, Instant.EPOCH);
        UUID currentCommandId = UUID.randomUUID();
        sync.acquireGraphOperation(
                currentCommandId.toString(),
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                Instant.EPOCH.plusSeconds(1)
        );
        when(syncRepository.findByProjectIdForUpdate(1))
                .thenReturn(Optional.of(sync));

        assertThat(guard.release(
                1,
                UUID.randomUUID(),
                "COMMAND_PUBLISH_FAILED"
        )).isFalse();
        assertThat(sync.getActiveCommandId())
                .isEqualTo(currentCommandId.toString());

        assertThat(guard.release(
                1,
                currentCommandId,
                "GRAPH_PROJECTION_APPLIED"
        )).isTrue();
        assertThat(sync.hasActiveCommand()).isFalse();
    }

    @Test
    void assertNoActiveOperationUsesLockedSyncWithoutChangingState() {
        ProjectGraphSync idle = ProjectGraphSync.initial(1, Instant.EPOCH);
        when(syncRepository.findByProjectIdForUpdate(1))
                .thenReturn(Optional.of(idle));

        guard.assertNoActiveOperation(1);

        assertThat(idle.hasActiveCommand()).isFalse();
    }

    @Test
    void assertNoActiveOperationRejectsActiveAndMissingSync() {
        ProjectGraphSync active = ProjectGraphSync.initial(1, Instant.EPOCH);
        active.acquireGraphOperation(
                UUID.randomUUID().toString(),
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                Instant.EPOCH.plusSeconds(1)
        );
        when(syncRepository.findByProjectIdForUpdate(1))
                .thenReturn(Optional.of(active));
        when(syncRepository.findByProjectIdForUpdate(2))
                .thenReturn(Optional.empty());

        assertThatThrownBy(() -> guard.assertNoActiveOperation(1))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(ProjectGraphOperationErrorCode.GRAPH_OPERATION_IN_PROGRESS);
        assertThat(active.hasActiveCommand()).isTrue();

        assertThatThrownBy(() -> guard.assertNoActiveOperation(2))
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(ProjectGraphOperationErrorCode.PROJECT_GRAPH_SYNC_NOT_FOUND);
    }
}
