package com.ssafy.projectree.domain.meeting.result.summary;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.summary.entity.MeetingSummaryProjection;
import com.ssafy.projectree.domain.meeting.result.summary.repository.MeetingSummaryProjectionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.Instant;

@Service
@RequiredArgsConstructor
public class MeetingSummaryProjectionService {

    private final MeetingSummaryProjectionRepository projectionRepository;
    private final Clock clock;

    @Transactional(propagation = Propagation.MANDATORY)
    public SummaryProjectionApplyResult apply(
            AnalysisResultEventEnvelope event,
            MeetingSummaryReadyPayload payload
    ) {
        Instant syncedAt = Instant.now(clock);
        MeetingSummaryProjection projection = projectionRepository.findByMeetingId(event.meetingId())
                .orElse(null);
        if (projection == null) {
            projectionRepository.saveAndFlush(MeetingSummaryProjection.create(
                    event.meetingId(),
                    event.projectId(),
                    event.commandId(),
                    payload,
                    event.occurredAt(),
                    syncedAt
            ));
            return SummaryProjectionApplyResult.CREATED;
        }
        boolean updated = projection.applyIfNewer(
                event.commandId(),
                payload,
                event.occurredAt(),
                syncedAt
        );
        return updated
                ? SummaryProjectionApplyResult.UPDATED
                : SummaryProjectionApplyResult.IGNORED_OLDER_VERSION;
    }
}
