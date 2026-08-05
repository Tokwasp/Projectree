package com.ssafy.projectree.domain.meeting.infrastructure.redis;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.meeting-sync")
public record MeetingSyncProperties(
        boolean enabled,
        long fixedDelayMs,
        long scanCount,
        String keyPrefix
) {

    public MeetingSyncProperties {
        if (fixedDelayMs <= 0) {
            throw new IllegalArgumentException("app.meeting-sync.fixed-delay-ms must be positive");
        }
        if (scanCount <= 0) {
            throw new IllegalArgumentException("app.meeting-sync.scan-count must be positive");
        }
        if (keyPrefix == null || keyPrefix.isBlank()) {
            throw new IllegalArgumentException("app.meeting-sync.key-prefix must not be blank");
        }
    }
}
