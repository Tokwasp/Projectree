package com.ssafy.projectree.domain.meeting.outbox.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.meeting-analysis.publisher")
public record MeetingAnalysisPublisherProperties(
        boolean enabled,
        long fixedDelayMs,
        int batchSize,
        int maxAttempts,
        long leaseDurationSeconds,
        long firstRetryDelaySeconds,
        long secondRetryDelaySeconds,
        long apiCallAttemptTimeoutSeconds,
        long apiCallTimeoutSeconds,
        String queueUrl,
        String region
) {
    public MeetingAnalysisPublisherProperties {
        if (fixedDelayMs <= 0 || batchSize <= 0) {
            throw new IllegalArgumentException("publisher interval and batch size must be positive");
        }
        if (maxAttempts != 3) {
            throw new IllegalArgumentException("meeting analysis commands must use exactly 3 attempts");
        }
        if (leaseDurationSeconds <= apiCallTimeoutSeconds) {
            throw new IllegalArgumentException("lease duration must be longer than API call timeout");
        }
        if (firstRetryDelaySeconds < 0 || secondRetryDelaySeconds < 0
                || apiCallAttemptTimeoutSeconds <= 0 || apiCallTimeoutSeconds <= 0) {
            throw new IllegalArgumentException("publisher timeout and retry delays are invalid");
        }
        if (apiCallAttemptTimeoutSeconds > apiCallTimeoutSeconds) {
            throw new IllegalArgumentException("attempt timeout must not exceed API call timeout");
        }
        if (region == null || region.isBlank()) {
            throw new IllegalArgumentException("AWS region must not be blank");
        }
        queueUrl = queueUrl == null ? "" : queueUrl;
    }
}
