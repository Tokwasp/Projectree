package com.ssafy.projectree.domain.meeting.smoke;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;
import software.amazon.awssdk.services.sqs.model.SendMessageResponse;

import java.time.Duration;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("smoke")
@EnabledIfEnvironmentVariable(
        named = "MEETING_ANALYSIS_SQS_SMOKE_ENABLED",
        matches = "(?i)true"
)
@EnabledIfEnvironmentVariable(
        named = "MEETING_ANALYSIS_SQS_SMOKE_ALLOW_SEND",
        matches = "(?i)true"
)
class MeetingAnalysisSqsSmokeTest {

    @Test
    void sendsExactPayloadToDedicatedSmokeQueue() {
        String queueUrl = required("MEETING_ANALYSIS_COMMAND_SMOKE_QUEUE_URL");
        String region = System.getenv().getOrDefault("AWS_REGION", "ap-northeast-2");
        String commandId = UUID.randomUUID().toString();
        String payload = "{\"smoke\":true,\"commandId\":\"" + commandId + "\"}";

        try (SqsClient client = SqsClient.builder()
                .region(Region.of(region))
                .credentialsProvider(DefaultCredentialsProvider.builder().build())
                .overrideConfiguration(configuration -> configuration
                        .retryStrategy(strategy -> strategy.maxAttempts(1))
                        .apiCallAttemptTimeout(Duration.ofSeconds(5))
                        .apiCallTimeout(Duration.ofSeconds(10)))
                .build()) {
            SendMessageResponse response = client.sendMessage(request -> request
                    .queueUrl(queueUrl)
                    .messageBody(payload));
            assertThat(response.messageId()).isNotBlank();
        }
    }

    private String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException(name + " is required");
        }
        return value;
    }
}
