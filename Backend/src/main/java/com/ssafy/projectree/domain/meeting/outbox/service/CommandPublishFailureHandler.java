package com.ssafy.projectree.domain.meeting.outbox.service;

import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.notification.entity.MeetingAnalysisNotificationOutbox;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationAudience;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.config.MeetingAnalysisPublisherProperties;
import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class CommandPublishFailureHandler {

    private final MeetingAnalysisCommandOutboxRepository outboxRepository;
    private final MeetingRepository meetingRepository;
    private final MeetingAnalysisNotificationOutboxRepository notificationRepository;
    private final MeetingAnalysisPublisherProperties properties;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public CommandPublishFailureOutcome handle(
            ClaimedCommandOutbox claimed,
            RuntimeException failure
    ) {
        MeetingAnalysisCommandOutbox outbox = outboxRepository
                .findOwnedPublishingForUpdate(claimed.outboxId(), claimed.claimToken())
                .orElse(null);
        if (outbox == null) {
            log.warn("Ignored stale publish failure. outboxId={}", claimed.outboxId());
            return CommandPublishFailureOutcome.STALE;
        }

        String safeError = sanitize(failure);
        boolean finalFailure = outbox.rescheduleOrFail(
                claimed.claimToken(),
                LocalDateTime.now(clock),
                properties.maxAttempts(),
                properties.firstRetryDelaySeconds(),
                properties.secondRetryDelaySeconds(),
                safeError
        );
        if (!finalFailure) {
            return CommandPublishFailureOutcome.RETRY_SCHEDULED;
        }

        if (outbox.getCommandType() == MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED) {
            log.error(
                    "Node content update command publish permanently failed. commandId={}, targetProjectId={}, targetNodeId={}, attemptCount={}",
                    outbox.getCommandId(),
                    outbox.getTargetProjectId(),
                    outbox.getTargetNodeId(),
                    outbox.getAttemptCount()
            );
            return CommandPublishFailureOutcome.FINAL_FAILED;
        }

        Meeting meeting = meetingRepository.findByIdForUpdate(outbox.getMeeting().getId())
                .orElseThrow(() -> new IllegalStateException("Meeting not found for command outbox"));
        failSelectedProcessingTasks(meeting);
        notificationRepository.saveAllAndFlush(createNotifications(outbox, meeting));
        return CommandPublishFailureOutcome.FINAL_FAILED;
    }

    private void failSelectedProcessingTasks(Meeting meeting) {
        if (meeting.isGenerateSummary()
                && meeting.getSummaryStatus() == AnalysisTaskStatus.PROCESSING) {
            meeting.markSummaryFailed();
        }
        if (meeting.isGenerateNodes()
                && meeting.getNodeStatus() == AnalysisTaskStatus.PROCESSING) {
            meeting.markNodesFailed();
        }
    }

    private List<MeetingAnalysisNotificationOutbox> createNotifications(
            MeetingAnalysisCommandOutbox outbox,
            Meeting meeting
    ) {
        int meetingId = meeting.getId();
        int projectId = meeting.getProject().getId();
        List<MeetingAnalysisNotificationOutbox> notifications = new ArrayList<>();
        if (meeting.isGenerateSummary() || meeting.isGenerateNodes()) {
            notifications.add(MeetingAnalysisNotificationOutbox.pending(
                    outbox.getCommandId(),
                    meetingId,
                    projectId,
                    outbox.getRequestedByMemberId(),
                    NotificationAudience.USER,
                    serialize(Map.of(
                            "message", "회의 분석 요청 전달에 실패했습니다.",
                            "meetingId", meetingId,
                            "projectId", projectId
                    ))
            ));
        }

        Map<String, Object> operationsPayload = new LinkedHashMap<>();
        operationsPayload.put("commandId", outbox.getCommandId());
        operationsPayload.put("meetingId", meetingId);
        operationsPayload.put("projectId", projectId);
        operationsPayload.put("attemptCount", outbox.getAttemptCount());
        operationsPayload.put("lastError", outbox.getLastError());
        notifications.add(MeetingAnalysisNotificationOutbox.pending(
                outbox.getCommandId(),
                meetingId,
                projectId,
                null,
                NotificationAudience.OPERATIONS,
                serialize(operationsPayload)
        ));
        return notifications;
    }

    private String serialize(Map<String, Object> payload) {
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JacksonException exception) {
            throw new IllegalStateException("Failed to serialize notification payload", exception);
        }
    }

    private String sanitize(RuntimeException failure) {
        return failure == null ? "RuntimeException" : failure.getClass().getSimpleName();
    }
}
