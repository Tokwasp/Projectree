package com.ssafy.projectree.domain.meeting.outbox.service;

import com.ssafy.projectree.domain.meeting.outbox.config.MeetingAnalysisPublisherProperties;
import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;

@Service
@RequiredArgsConstructor
public class CommandOutboxClaimService {

    private final MeetingAnalysisCommandOutboxRepository outboxRepository;
    private final MeetingAnalysisPublisherProperties properties;
    private final Clock clock;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public List<ClaimedCommandOutbox> claimAvailable() {
        LocalDateTime now = LocalDateTime.now(clock);
        LocalDateTime leaseUntil = now.plusSeconds(properties.leaseDurationSeconds());
        return outboxRepository.findClaimableForUpdate(
                        now,
                        properties.maxAttempts(),
                        properties.batchSize()
                ).stream()
                .map(outbox -> claim(outbox, now, leaseUntil))
                .toList();
    }

    private ClaimedCommandOutbox claim(
            MeetingAnalysisCommandOutbox outbox,
            LocalDateTime now,
            LocalDateTime leaseUntil
    ) {
        String claimToken = outbox.claim(now, leaseUntil, properties.maxAttempts());
        return new ClaimedCommandOutbox(
                outbox.getId(),
                outbox.getCommandId(),
                outbox.getCommandType(),
                outbox.getPayload(),
                claimToken,
                outbox.getAttemptCount()
        );
    }
}
