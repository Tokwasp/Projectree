package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.mail.repository.InvitationMailRepository;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.infrastructure.redis.MeetingRoomRedisReader;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationErrorCode;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.inbox.repository.MeetingAnalysisResultInboxRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.summary.repository.MeetingSummaryProjectionRepository;
import com.ssafy.projectree.domain.meetingreview.repository.MeetingReviewRepository;
import com.ssafy.projectree.domain.project.repository.ProjectInvitationRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Slf4j
@Service
@RequiredArgsConstructor
public class ProjectDeletionService {

    private final MeetingRoomRedisReader meetingRoomRedisReader;
    private final MeetingRepository meetingRepository;
    private final InvitationMailRepository invitationMailRepository;
    private final ProjectInvitationRepository projectInvitationRepository;
    private final NodeEvidenceProjectionRepository nodeEvidenceProjectionRepository;
    private final ProjectNodeProjectionRepository projectNodeProjectionRepository;
    private final NodeDeleteCommandItemRepository nodeDeleteCommandItemRepository;
    private final NodeDeleteCommandRepository nodeDeleteCommandRepository;
    private final MeetingRecordRepository meetingRecordRepository;
    private final MeetingAnalysisCommandOutboxRepository commandOutboxRepository;
    private final MeetingSummaryProjectionRepository summaryProjectionRepository;
    private final MeetingAnalysisResultInboxRepository resultInboxRepository;
    private final MeetingAnalysisNotificationOutboxRepository notificationOutboxRepository;
    private final MeetingReviewRepository meetingReviewRepository;
    private final ProjectGraphSyncRepository projectGraphSyncRepository;
    private final ProjectGraphOperationGuard projectGraphOperationGuard;
    private final ProjectMemberRepository projectMemberRepository;
    private final ProjectRepository projectRepository;

    @Transactional
    public void deleteProjectAggregate(int projectId) {
        assertDeletable(projectId);

        invitationMailRepository.deleteAllByProjectId(projectId);
        projectInvitationRepository.deleteAllByProjectId(projectId);

        nodeEvidenceProjectionRepository.deleteAllByProjectId(projectId);
        projectNodeProjectionRepository.deleteAllByProjectId(projectId);

        meetingRecordRepository.deleteAllByProjectId(projectId);
        nodeDeleteCommandItemRepository.deleteAllByProjectId(projectId);
        nodeDeleteCommandRepository.deleteAllByProjectId(projectId);
        commandOutboxRepository.deleteAllByProjectId(projectId);

        summaryProjectionRepository.deleteAllByProjectId(projectId);
        resultInboxRepository.deleteAllByProjectId(projectId);
        notificationOutboxRepository.deleteAllByProjectId(projectId);
        meetingReviewRepository.deleteAllByProjectId(projectId);

        meetingRepository.deleteAllByProjectId(projectId);
        projectGraphSyncRepository.deleteAllByProjectId(projectId);
        projectMemberRepository.deleteByProjectId(projectId);
        projectRepository.deleteById(projectId);
    }

    private void assertDeletable(int projectId) {
        assertNoActiveMeetingRoom(projectId);
        if (meetingRepository.existsProcessingAnalysisByProjectId(
                projectId,
                AnalysisTaskStatus.PROCESSING
        )) {
            throw new CustomException(ProjectErrorCode.PROJECT_DELETE_ANALYSIS_IN_PROGRESS);
        }
        assertNoActiveGraphOperation(projectId);
        if (commandOutboxRepository.existsInFlightGraphMutationByProjectId(
                projectId,
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                MeetingAnalysisOutboxStatus.FAILED,
                AnalysisResultEventType.PROJECT_GRAPH_CHANGED
        )) {
            throw new CustomException(ProjectErrorCode.PROJECT_DELETE_GRAPH_OPERATION_IN_PROGRESS);
        }
    }

    private void assertNoActiveMeetingRoom(int projectId) {
        try {
            if (meetingRoomRedisReader.existsByProjectId(projectId)) {
                throw new CustomException(ProjectErrorCode.PROJECT_DELETE_ACTIVE_MEETING);
            }
        } catch (CustomException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            log.error("[Project] PROJECT_DELETE_STATE_CHECK_FAILED. projectId={}", projectId, exception);
            throw new CustomException(ProjectErrorCode.PROJECT_DELETE_STATE_CHECK_FAILED);
        }
    }

    private void assertNoActiveGraphOperation(int projectId) {
        try {
            projectGraphOperationGuard.assertNoActiveOperation(projectId);
        } catch (CustomException exception) {
            if (exception.getErrorCode()
                    == ProjectGraphOperationErrorCode.GRAPH_OPERATION_IN_PROGRESS) {
                throw new CustomException(ProjectErrorCode.PROJECT_DELETE_GRAPH_OPERATION_IN_PROGRESS);
            }
            throw exception;
        }
    }
}
