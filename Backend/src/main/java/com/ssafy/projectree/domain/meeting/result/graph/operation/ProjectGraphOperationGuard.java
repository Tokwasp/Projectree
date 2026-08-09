package com.ssafy.projectree.domain.meeting.result.graph.operation;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.Objects;
import java.util.UUID;

@Slf4j
@Component
@RequiredArgsConstructor
public class ProjectGraphOperationGuard {

    private final ProjectGraphSyncRepository syncRepository;

    public ProjectGraphSync acquire(
            int projectId,
            UUID commandId,
            MeetingAnalysisCommandType commandType,
            Instant acquiredAt
    ) {
        Objects.requireNonNull(commandId, "commandId must not be null");
        ProjectGraphSync sync = findLocked(projectId);
        if (sync.hasActiveCommand()) {
            log.info(
                    "[AnalysisFlow] GRAPH_OPERATION_GUARD_REJECTED. projectId={}, requestedCommandId={}, requestedCommandType={}, activeCommandId={}, activeCommandType={}, activeSince={}",
                    projectId,
                    commandId,
                    commandType,
                    sync.getActiveCommandId(),
                    sync.getActiveCommandType(),
                    sync.getActiveSince()
            );
            throw new CustomException(
                    ProjectGraphOperationErrorCode.GRAPH_OPERATION_IN_PROGRESS
            );
        }

        sync.acquireGraphOperation(commandId.toString(), commandType, acquiredAt);
        log.info(
                "[AnalysisFlow] GRAPH_OPERATION_GUARD_ACQUIRED. projectId={}, commandId={}, commandType={}, activeSince={}",
                projectId,
                commandId,
                commandType,
                acquiredAt
        );
        return sync;
    }

    public void assertNoActiveOperation(int projectId) {
        ProjectGraphSync sync = findLocked(projectId);
        if (!sync.hasActiveCommand()) {
            return;
        }
        log.info(
                "[AnalysisFlow] PROJECT_DELETE_BLOCKED_BY_GRAPH_OPERATION. projectId={}, activeCommandId={}, activeCommandType={}, activeSince={}",
                projectId,
                sync.getActiveCommandId(),
                sync.getActiveCommandType(),
                sync.getActiveSince()
        );
        throw new CustomException(
                ProjectGraphOperationErrorCode.GRAPH_OPERATION_IN_PROGRESS
        );
    }

    public boolean release(
            int projectId,
            UUID commandId,
            String releaseReason
    ) {
        Objects.requireNonNull(commandId, "commandId must not be null");
        return release(findLocked(projectId), commandId.toString(), releaseReason);
    }

    public boolean release(
            int projectId,
            String commandId,
            String releaseReason
    ) {
        return release(findLocked(projectId), commandId, releaseReason);
    }

    public boolean release(
            ProjectGraphSync sync,
            String commandId,
            String releaseReason
    ) {
        MeetingAnalysisCommandType activeCommandType = sync.getActiveCommandType();
        String activeCommandId = sync.getActiveCommandId();
        boolean released = sync.releaseGraphOperation(commandId);
        if (released) {
            log.info(
                    "[AnalysisFlow] GRAPH_OPERATION_GUARD_RELEASED. projectId={}, commandId={}, commandType={}, releaseReason={}",
                    sync.getProjectId(),
                    commandId,
                    activeCommandType,
                    releaseReason
            );
            return true;
        }

        log.warn(
                "[AnalysisFlow] GRAPH_OPERATION_GUARD_RELEASE_SKIPPED. projectId={}, requestedCommandId={}, activeCommandId={}, activeCommandType={}, releaseReason={}",
                sync.getProjectId(),
                commandId,
                activeCommandId,
                activeCommandType,
                releaseReason
        );
        return false;
    }

    private ProjectGraphSync findLocked(int projectId) {
        return syncRepository.findByProjectIdForUpdate(projectId)
                .orElseThrow(() -> new CustomException(
                        ProjectGraphOperationErrorCode.PROJECT_GRAPH_SYNC_NOT_FOUND
                ));
    }
}
