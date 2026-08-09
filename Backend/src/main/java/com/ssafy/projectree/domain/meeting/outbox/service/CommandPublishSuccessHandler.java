package com.ssafy.projectree.domain.meeting.outbox.service;

import com.ssafy.projectree.domain.meeting.outbox.dto.ClaimedCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Clock;
import java.time.LocalDateTime;

@Slf4j
@Service
@RequiredArgsConstructor
public class CommandPublishSuccessHandler {

    private final MeetingAnalysisCommandOutboxRepository outboxRepository;
    private final Clock clock;

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public boolean handle(ClaimedCommandOutbox claimed) {
        return outboxRepository.findOwnedPublishingForUpdate(
                        claimed.outboxId(),
                        claimed.claimToken()
                )
                .map(outbox -> outbox.markPublished(
                        claimed.claimToken(),
                        LocalDateTime.now(clock)
                ))
                .orElseGet(() -> {
                    log.warn("Ignored stale publish success. outboxId={}", claimed.outboxId());
                    return false;
                });
    }
}
