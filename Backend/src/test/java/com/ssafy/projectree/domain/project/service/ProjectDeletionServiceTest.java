package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.mail.repository.InvitationMailRepository;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
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
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InOrder;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.inOrder;
import static org.mockito.Mockito.verifyNoInteractions;

@ExtendWith(MockitoExtension.class)
class ProjectDeletionServiceTest {

    private static final int PROJECT_ID = 7;

    @InjectMocks private ProjectDeletionService projectDeletionService;
    @Mock private MeetingRoomRedisReader meetingRoomRedisReader;
    @Mock private MeetingRepository meetingRepository;
    @Mock private InvitationMailRepository invitationMailRepository;
    @Mock private ProjectInvitationRepository projectInvitationRepository;
    @Mock private NodeEvidenceProjectionRepository nodeEvidenceProjectionRepository;
    @Mock private ProjectNodeProjectionRepository projectNodeProjectionRepository;
    @Mock private NodeDeleteCommandItemRepository nodeDeleteCommandItemRepository;
    @Mock private NodeDeleteCommandRepository nodeDeleteCommandRepository;
    @Mock private MeetingRecordRepository meetingRecordRepository;
    @Mock private MeetingAnalysisCommandOutboxRepository commandOutboxRepository;
    @Mock private MeetingSummaryProjectionRepository summaryProjectionRepository;
    @Mock private MeetingAnalysisResultInboxRepository resultInboxRepository;
    @Mock private MeetingAnalysisNotificationOutboxRepository notificationOutboxRepository;
    @Mock private MeetingReviewRepository meetingReviewRepository;
    @Mock private ProjectGraphSyncRepository projectGraphSyncRepository;
    @Mock private ProjectGraphOperationGuard projectGraphOperationGuard;
    @Mock private ProjectMemberRepository projectMemberRepository;
    @Mock private ProjectRepository projectRepository;

    @Test
    void deletesAggregateChildrenBeforeProject() {
        given(meetingRepository.existsProcessingAnalysisByProjectId(
                PROJECT_ID,
                AnalysisTaskStatus.PROCESSING
        )).willReturn(false);

        projectDeletionService.deleteProjectAggregate(PROJECT_ID);

        InOrder order = inOrder(
                invitationMailRepository,
                projectInvitationRepository,
                nodeEvidenceProjectionRepository,
                projectNodeProjectionRepository,
                meetingRecordRepository,
                nodeDeleteCommandItemRepository,
                nodeDeleteCommandRepository,
                commandOutboxRepository,
                summaryProjectionRepository,
                resultInboxRepository,
                notificationOutboxRepository,
                meetingReviewRepository,
                meetingRepository,
                projectGraphSyncRepository,
                projectMemberRepository,
                projectRepository
        );
        order.verify(invitationMailRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(projectInvitationRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(nodeEvidenceProjectionRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(projectNodeProjectionRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(meetingRecordRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(nodeDeleteCommandItemRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(nodeDeleteCommandRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(commandOutboxRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(summaryProjectionRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(resultInboxRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(notificationOutboxRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(meetingReviewRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(meetingRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(projectGraphSyncRepository).deleteAllByProjectId(PROJECT_ID);
        order.verify(projectMemberRepository).deleteByProjectId(PROJECT_ID);
        order.verify(projectRepository).deleteById(PROJECT_ID);
    }

    @Test
    void rejectsDeletionWhenActiveMeetingRoomExists() {
        given(meetingRoomRedisReader.existsByProjectId(PROJECT_ID)).willReturn(true);

        assertThatThrownBy(() -> projectDeletionService.deleteProjectAggregate(PROJECT_ID))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_ACTIVE_MEETING);

        verifyNoInteractions(meetingRepository, projectRepository);
    }

    @Test
    void rejectsDeletionWhenAnalysisIsProcessing() {
        given(meetingRepository.existsProcessingAnalysisByProjectId(
                PROJECT_ID,
                AnalysisTaskStatus.PROCESSING
        )).willReturn(true);

        assertThatThrownBy(() -> projectDeletionService.deleteProjectAggregate(PROJECT_ID))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_ANALYSIS_IN_PROGRESS);

        verifyNoInteractions(projectRepository);
    }

    @Test
    void failsClosedWhenMeetingRoomStateCannotBeRead() {
        given(meetingRoomRedisReader.existsByProjectId(PROJECT_ID))
                .willThrow(new IllegalStateException("redis unavailable"));

        assertThatThrownBy(() -> projectDeletionService.deleteProjectAggregate(PROJECT_ID))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_STATE_CHECK_FAILED);

        verifyNoInteractions(meetingRepository, projectRepository);
    }

    @Test
    void rejectsDeletionWhenNodeContentUpdateIsInFlight() {
        given(meetingRepository.existsProcessingAnalysisByProjectId(
                PROJECT_ID,
                AnalysisTaskStatus.PROCESSING
        )).willReturn(false);
        given(commandOutboxRepository.existsInFlightGraphMutationByProjectId(
                PROJECT_ID,
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                MeetingAnalysisOutboxStatus.FAILED,
                AnalysisResultEventType.PROJECT_GRAPH_CHANGED
        )).willReturn(true);

        assertThatThrownBy(() -> projectDeletionService.deleteProjectAggregate(PROJECT_ID))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_GRAPH_OPERATION_IN_PROGRESS);

        verifyNoInteractions(projectRepository);
    }

    @Test
    void translatesActiveGraphGuardErrorToProjectDeletionError() {
        given(meetingRepository.existsProcessingAnalysisByProjectId(
                PROJECT_ID,
                AnalysisTaskStatus.PROCESSING
        )).willReturn(false);
        doThrow(new CustomException(
                ProjectGraphOperationErrorCode.GRAPH_OPERATION_IN_PROGRESS
        )).when(projectGraphOperationGuard).assertNoActiveOperation(PROJECT_ID);

        assertThatThrownBy(() -> projectDeletionService.deleteProjectAggregate(PROJECT_ID))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_GRAPH_OPERATION_IN_PROGRESS);

        verifyNoInteractions(projectRepository, commandOutboxRepository);
    }

    @Test
    void propagatesNonConflictGraphGuardError() {
        given(meetingRepository.existsProcessingAnalysisByProjectId(
                PROJECT_ID,
                AnalysisTaskStatus.PROCESSING
        )).willReturn(false);
        doThrow(new CustomException(
                ProjectGraphOperationErrorCode.PROJECT_GRAPH_SYNC_NOT_FOUND
        )).when(projectGraphOperationGuard).assertNoActiveOperation(PROJECT_ID);

        assertThatThrownBy(() -> projectDeletionService.deleteProjectAggregate(PROJECT_ID))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectGraphOperationErrorCode.PROJECT_GRAPH_SYNC_NOT_FOUND);

        verifyNoInteractions(projectRepository, commandOutboxRepository);
    }
}
