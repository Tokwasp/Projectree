package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.notification.entity.MeetingAnalysisNotificationOutbox;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationAudience;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationType;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.exception.InvalidAnalysisTaskStateException;
import com.ssafy.projectree.domain.meeting.result.failure.AnalysisTaskStatusChangedPayload;
import com.ssafy.projectree.domain.meeting.result.failure.AnalysisTaskStatusChangedPayloadParser;
import com.ssafy.projectree.domain.meeting.result.failure.AnalysisTaskStatusChangedPayloadValidator;
import com.ssafy.projectree.domain.meeting.result.failure.AnalysisTaskType;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import com.ssafy.projectree.domain.meeting.result.validation.LockedAnalysisEventReferenceValidator;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.util.LinkedHashMap;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class AnalysisFailureEventHandler implements AnalysisResultEventHandler {

    private final AnalysisTaskStatusChangedPayloadParser payloadParser;
    private final AnalysisTaskStatusChangedPayloadValidator payloadValidator;
    private final MeetingRepository meetingRepository;
    private final LockedAnalysisEventReferenceValidator lockedReferenceValidator;
    private final ResultInboxService resultInboxService;
    private final MeetingAnalysisNotificationOutboxRepository notificationOutboxRepository;
    private final ObjectMapper objectMapper;
    private final ProjectGraphOperationGuard graphOperationGuard;

    @Override
    public AnalysisResultEventType supportedType() {
        return AnalysisResultEventType.ANALYSIS_TASK_STATUS_CHANGED;
    }

    @Override
    @Transactional
    public void handle(AnalysisResultEventEnvelope event) {
        AnalysisTaskStatusChangedPayload payload = payloadParser.parse(event.payload());
        payloadValidator.validate(payload);

        Meeting meeting = meetingRepository.findByIdForUpdate(event.meetingId())
                .orElseThrow(() -> new AnalysisResultContractException("Analysis result meeting does not exist"));
        MeetingAnalysisCommandOutbox command = lockedReferenceValidator.validate(event, meeting);

        resultInboxService.registerProcessed(event);

        boolean changed = applyFailure(meeting, payload.taskType());
        if (changed) {
            notificationOutboxRepository.saveAndFlush(createNotification(command, meeting, event, payload));
        }
        if (changed && payload.taskType() == AnalysisTaskType.NODES) {
            if (!graphOperationGuard.release(
                    event.projectId(),
                    event.commandId(),
                    "ANALYSIS_TERMINAL_FAILED"
            )) {
                throw new AnalysisResultContractException(
                        "Analysis failure result does not own the active graph operation"
                );
            }
        }
    }

    private boolean applyFailure(Meeting meeting, AnalysisTaskType taskType) {
        try {
            return switch (taskType) {
                case SUMMARY -> meeting.failSummaryAnalysis();
                case NODES -> meeting.failNodeAnalysis();
            };
        } catch (IllegalStateException exception) {
            throw new InvalidAnalysisTaskStateException(
                    "Analysis task cannot receive a failure event", exception
            );
        }
    }

    private MeetingAnalysisNotificationOutbox createNotification(
            MeetingAnalysisCommandOutbox command,
            Meeting meeting,
            AnalysisResultEventEnvelope event,
            AnalysisTaskStatusChangedPayload payload
    ) {
        return MeetingAnalysisNotificationOutbox.pending(
                command.getCommandId(),
                meeting.getId(),
                event.projectId(),
                command.getRequestedByMemberId(),
                NotificationAudience.USER,
                notificationType(payload.taskType()),
                serializeNotificationPayload(command, meeting, event, payload)
        );
    }

    private NotificationType notificationType(AnalysisTaskType taskType) {
        return switch (taskType) {
            case SUMMARY -> NotificationType.MEETING_SUMMARY_ANALYSIS_FAILED;
            case NODES -> NotificationType.MEETING_NODE_ANALYSIS_FAILED;
        };
    }

    private String serializeNotificationPayload(
            MeetingAnalysisCommandOutbox command,
            Meeting meeting,
            AnalysisResultEventEnvelope event,
            AnalysisTaskStatusChangedPayload payload
    ) {
        Map<String, Object> notificationPayload = new LinkedHashMap<>();
        notificationPayload.put("recipientMemberId", command.getRequestedByMemberId());
        notificationPayload.put("projectId", event.projectId());
        notificationPayload.put("meetingId", meeting.getId());
        notificationPayload.put("roomName", meeting.getRoomName());
        notificationPayload.put("taskType", payload.taskType());
        notificationPayload.put("failureCode", payload.failureCode());
        notificationPayload.put("failureMessage", payload.failureMessage());
        notificationPayload.put("occurredAt", event.occurredAt());
        try {
            return objectMapper.writeValueAsString(notificationPayload);
        } catch (JacksonException exception) {
            throw new IllegalStateException("Failed to serialize analysis failure notification", exception);
        }
    }
}
