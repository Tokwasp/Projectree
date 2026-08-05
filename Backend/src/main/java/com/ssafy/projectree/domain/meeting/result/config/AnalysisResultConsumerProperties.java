package com.ssafy.projectree.domain.meeting.result.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.meeting-analysis.result-consumer")
public record AnalysisResultConsumerProperties(
        boolean enabled,
        String queueUrl,
        int waitTimeSeconds,
        int maxNumberOfMessages,
        long pollingDelayMs,
        String region
) {
    public AnalysisResultConsumerProperties {
        queueUrl = queueUrl == null ? "" : queueUrl;
        if (enabled && queueUrl.isBlank()) {
            throw new IllegalArgumentException(
                    "AWS_ANALYSIS_RESULT_QUEUE_URL is required when meeting analysis result consumer is enabled."
            );
        }
        if (waitTimeSeconds < 0 || waitTimeSeconds > 20) {
            throw new IllegalArgumentException("SQS wait time seconds must be between 0 and 20");
        }
        if (maxNumberOfMessages < 1 || maxNumberOfMessages > 10) {
            throw new IllegalArgumentException("SQS max number of messages must be between 1 and 10");
        }
        if (pollingDelayMs <= 0) {
            throw new IllegalArgumentException("SQS polling delay must be positive");
        }
        if (region == null || region.isBlank()) {
            throw new IllegalArgumentException("AWS region must not be blank");
        }
    }
}
