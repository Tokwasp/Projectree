package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskCompletionResult;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.notification.entity.MeetingAnalysisNotificationOutbox;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationAudience;
import com.ssafy.projectree.domain.meeting.notification.entity.NotificationType;
import com.ssafy.projectree.domain.meeting.notification.repository.MeetingAnalysisNotificationOutboxRepository;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.exception.InvalidAnalysisTaskStateException;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import com.ssafy.projectree.domain.meeting.result.validation.LockedAnalysisEventReferenceValidator;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import jakarta.persistence.EntityManager;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

@Service
@RequiredArgsConstructor
public class AnalysisGraphProjectionApplier {

    private final ProjectRepository projectRepository;
    private final MeetingRepository meetingRepository;
    private final LockedAnalysisEventReferenceValidator lockedReferenceValidator;
    private final ProjectGraphSyncRepository graphSyncRepository;
    private final ResultInboxService resultInboxService;
    private final GraphProjectionReplacer projectionReplacer;
    private final MeetingAnalysisNotificationOutboxRepository notificationOutboxRepository;
    private final EntityManager entityManager;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Transactional
    public GraphProjectionApplyResult apply(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            ProjectGraphSnapshot snapshot
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(payload, "payload must not be null");
        Objects.requireNonNull(snapshot, "snapshot must not be null");
        if (payload.sourceType() != GraphResultSourceType.MEETING_ANALYSIS) {
            throw new AnalysisResultContractException(
                    "Graph result sourceType does not match meeting analysis"
            );
        }
        if (event.meetingId() == null || event.meetingId() <= 0) {
            throw new AnalysisResultContractException(
                    "Meeting analysis result meetingId must be positive"
            );
        }

        projectRepository.findByIdForUpdate(event.projectId())
                .orElseThrow(() -> new AnalysisResultContractException("Analysis result project does not exist"));
        Meeting meeting = meetingRepository.findByIdForUpdate(event.meetingId())
                .orElseThrow(() -> new AnalysisResultContractException("Analysis result meeting does not exist"));
        MeetingAnalysisCommandOutbox command = lockedReferenceValidator.validate(event, meeting);
        ProjectGraphSync sync = findOrCreateLockedSync(event.projectId());

        resultInboxService.registerProcessed(event);

        AnalysisTaskCompletionResult completion = completeNodeAnalysis(meeting);
        if (completion == AnalysisTaskCompletionResult.ALREADY_FAILED) {
            return result(completion, false, payload, sync);
        }

        boolean projectionUpdated = payload.graphVersion() > sync.getCurrentGraphVersion();
        Instant syncedAt = Instant.now(clock);
        GraphApplyContext context = new GraphApplyContext(
                command.getCommandId(),
                command.getRequestedByMemberId(),
                meeting.getRoomName(),
                event.projectId(),
                meeting.getId(),
                completion,
                payload.graphVersion(),
                syncedAt
        );
        if (projectionUpdated) {
            entityManager.flush();
            entityManager.clear();
            projectionReplacer.replace(event.projectId(), snapshot, syncedAt);
            sync = graphSyncRepository.findByProjectIdForUpdate(event.projectId())
                    .orElseThrow(() -> new IllegalStateException("Project graph sync disappeared during replacement"));
            sync.advanceTo(context.requestedGraphVersion(), context.commandId(), context.syncedAt());
        }
        if (context.completionResult() == AnalysisTaskCompletionResult.APPLIED) {
            notificationOutboxRepository.saveAndFlush(
                    createSuccessNotification(context, event, sync.getCurrentGraphVersion(), projectionUpdated)
            );
        }
        return new GraphProjectionApplyResult(
                context.completionResult(),
                projectionUpdated,
                context.requestedGraphVersion(),
                sync.getCurrentGraphVersion()
        );
    }

    private ProjectGraphSync findOrCreateLockedSync(int projectId) {
        return graphSyncRepository.findByProjectIdForUpdate(projectId)
                .orElseGet(() -> graphSyncRepository.saveAndFlush(
                        ProjectGraphSync.initial(projectId, Instant.now(clock))
                ));
    }

    private AnalysisTaskCompletionResult completeNodeAnalysis(Meeting meeting) {
        try {
            return meeting.completeNodeAnalysis();
        } catch (IllegalStateException exception) {
            throw new InvalidAnalysisTaskStateException(
                    "Node task cannot receive a success event", exception
            );
        }
    }

    private GraphProjectionApplyResult result(
            AnalysisTaskCompletionResult completion,
            boolean projectionUpdated,
            ProjectGraphChangedPayload payload,
            ProjectGraphSync sync
    ) {
        return new GraphProjectionApplyResult(
                completion,
                projectionUpdated,
                payload.graphVersion(),
                sync.getCurrentGraphVersion()
        );
    }

    private MeetingAnalysisNotificationOutbox createSuccessNotification(
            GraphApplyContext context,
            AnalysisResultEventEnvelope event,
            long currentGraphVersion,
            boolean projectionUpdated
    ) {
        return MeetingAnalysisNotificationOutbox.pending(
                context.commandId(),
                context.meetingId(),
                context.projectId(),
                context.requestedByMemberId(),
                NotificationAudience.USER,
                NotificationType.MEETING_NODE_ANALYSIS_SUCCEEDED,
                serializeNotificationPayload(context, event, currentGraphVersion, projectionUpdated)
        );
    }

    private String serializeNotificationPayload(
            GraphApplyContext context,
            AnalysisResultEventEnvelope event,
            long currentGraphVersion,
            boolean projectionUpdated
    ) {
        Map<String, Object> notificationPayload = new LinkedHashMap<>();
        notificationPayload.put("recipientMemberId", context.requestedByMemberId());
        notificationPayload.put("projectId", context.projectId());
        notificationPayload.put("meetingId", context.meetingId());
        notificationPayload.put("roomName", context.roomName());
        notificationPayload.put("requestedGraphVersion", context.requestedGraphVersion());
        notificationPayload.put("currentGraphVersion", currentGraphVersion);
        notificationPayload.put("projectionUpdated", projectionUpdated);
        notificationPayload.put("occurredAt", event.occurredAt());
        try {
            return objectMapper.writeValueAsString(notificationPayload);
        } catch (JacksonException exception) {
            throw new IllegalStateException("Failed to serialize graph success notification", exception);
        }
    }

    private record GraphApplyContext(
            String commandId,
            int requestedByMemberId,
            String roomName,
            int projectId,
            int meetingId,
            AnalysisTaskCompletionResult completionResult,
            long requestedGraphVersion,
            Instant syncedAt
    ) {
    }
}
