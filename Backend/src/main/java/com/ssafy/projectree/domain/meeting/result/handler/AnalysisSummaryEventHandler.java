package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskCompletionResult;
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
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import com.ssafy.projectree.domain.meeting.result.summary.MeetingSummaryProjectionService;
import com.ssafy.projectree.domain.meeting.result.summary.MeetingSummaryReadyPayload;
import com.ssafy.projectree.domain.meeting.result.summary.MeetingSummaryReadyPayloadParser;
import com.ssafy.projectree.domain.meeting.result.summary.MeetingSummaryReadyPayloadValidator;
import com.ssafy.projectree.domain.meeting.result.summary.SummaryProjectionApplyResult;
import com.ssafy.projectree.domain.meeting.result.validation.LockedAnalysisEventReferenceValidator;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.util.LinkedHashMap;
import java.util.Map;

@Service
@Slf4j
@RequiredArgsConstructor
public class AnalysisSummaryEventHandler implements AnalysisResultEventHandler {

    private final MeetingSummaryReadyPayloadParser payloadParser;
    private final MeetingSummaryReadyPayloadValidator payloadValidator;
    private final MeetingRepository meetingRepository;
    private final LockedAnalysisEventReferenceValidator lockedReferenceValidator;
    private final ResultInboxService resultInboxService;
    private final MeetingSummaryProjectionService projectionService;
    private final MeetingAnalysisNotificationOutboxRepository notificationOutboxRepository;
    private final ObjectMapper objectMapper;

    @Override
    public AnalysisResultEventType supportedType() {
        return AnalysisResultEventType.MEETING_SUMMARY_READY;
    }

    @Override
    @Transactional
    public void handle(AnalysisResultEventEnvelope event) {
        MeetingSummaryReadyPayload payload = payloadValidator.validate(
                payloadParser.parse(event.payload()), event
        );
        Meeting meeting = meetingRepository.findByIdForUpdate(event.meetingId())
                .orElseThrow(() -> new AnalysisResultContractException("Analysis result meeting does not exist"));
        MeetingAnalysisCommandOutbox command = lockedReferenceValidator.validate(event, meeting);

        resultInboxService.registerProcessed(event);

        AnalysisTaskCompletionResult completion = completeSummary(meeting);
        SummaryProjectionApplyResult projectionResult = null;
        if (completion != AnalysisTaskCompletionResult.ALREADY_FAILED) {
            projectionResult = projectionService.apply(event, payload);
        }
        if (completion == AnalysisTaskCompletionResult.APPLIED) {
            notificationOutboxRepository.saveAndFlush(createNotification(command, meeting, event, payload));
        }
        if (projectionResult != null) {
            log.info(
                    "[AnalysisFlow] SUMMARY_PROJECTION_APPLIED. eventId={}, commandId={}, projectId={}, meetingId={}, summaryVersion={}, status={}, completionResult={}, projectionResult={}",
                    event.eventId(),
                    event.commandId(),
                    event.projectId(),
                    event.meetingId(),
                    payload.summaryVersion(),
                    payload.status(),
                    completion,
                    projectionResult
            );
        }
    }

    private AnalysisTaskCompletionResult completeSummary(Meeting meeting) {
        try {
            return meeting.completeSummaryAnalysis();
        } catch (IllegalStateException exception) {
            throw new InvalidAnalysisTaskStateException(
                    "Summary task cannot receive a success event", exception
            );
        }
    }

    private MeetingAnalysisNotificationOutbox createNotification(
            MeetingAnalysisCommandOutbox command,
            Meeting meeting,
            AnalysisResultEventEnvelope event,
            MeetingSummaryReadyPayload payload
    ) {
        return MeetingAnalysisNotificationOutbox.pending(
                command.getCommandId(),
                meeting.getId(),
                event.projectId(),
                command.getRequestedByMemberId(),
                NotificationAudience.USER,
                NotificationType.MEETING_SUMMARY_ANALYSIS_SUCCEEDED,
                serializeNotificationPayload(command, meeting, event, payload)
        );
    }

    private String serializeNotificationPayload(
            MeetingAnalysisCommandOutbox command,
            Meeting meeting,
            AnalysisResultEventEnvelope event,
            MeetingSummaryReadyPayload payload
    ) {
        Map<String, Object> notificationPayload = new LinkedHashMap<>();
        notificationPayload.put("recipientMemberId", command.getRequestedByMemberId());
        notificationPayload.put("projectId", event.projectId());
        notificationPayload.put("meetingId", meeting.getId());
        notificationPayload.put("roomName", meeting.getRoomName());
        notificationPayload.put("meetingSummaryId", payload.meetingSummaryId());
        notificationPayload.put("summaryVersion", payload.summaryVersion());
        notificationPayload.put("status", payload.status());
        notificationPayload.put("apiPath", payload.apiPath());
        notificationPayload.put("occurredAt", event.occurredAt());
        try {
            return objectMapper.writeValueAsString(notificationPayload);
        } catch (JacksonException exception) {
            throw new IllegalStateException("Failed to serialize summary notification", exception);
        }
    }
}
