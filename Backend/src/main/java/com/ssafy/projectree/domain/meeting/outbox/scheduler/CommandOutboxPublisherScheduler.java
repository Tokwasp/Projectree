package com.ssafy.projectree.domain.meeting.outbox.scheduler;

import com.ssafy.projectree.domain.meeting.outbox.publisher.CommandOutboxPublisher;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Slf4j
@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        prefix = "app.meeting-analysis.publisher",
        name = "enabled",
        havingValue = "true"
)
public class CommandOutboxPublisherScheduler {

    private final CommandOutboxPublisher publisher;

    @Scheduled(
            fixedDelayString =
                    "${app.meeting-analysis.publisher.fixed-delay-ms:1000}"
    )
    public void publish() {
        try {
            publisher.publishAvailable();
        } catch (RuntimeException claimFailure) {
            log.error("Meeting analysis command claim failed. Current cycle is aborted.", claimFailure);
        }
    }
}
