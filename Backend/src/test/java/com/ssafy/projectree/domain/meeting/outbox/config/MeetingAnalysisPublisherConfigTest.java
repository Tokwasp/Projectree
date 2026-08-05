package com.ssafy.projectree.domain.meeting.outbox.config;

import org.junit.jupiter.api.Test;
import software.amazon.awssdk.services.sqs.SqsClient;

import java.time.Duration;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingAnalysisPublisherConfigTest {

    @Test
    void sqsClientUsesSingleAttemptAndConfiguredTimeouts() {
        MeetingAnalysisPublisherProperties properties = properties(60, 5, 10);
        MeetingAnalysisPublisherConfig config = new MeetingAnalysisPublisherConfig();

        try (SqsClient client = config.meetingAnalysisSqsClient(properties)) {
            var override = client.serviceClientConfiguration().overrideConfiguration();
            assertThat(override.retryStrategy()).isPresent();
            assertThat(override.retryStrategy().orElseThrow().maxAttempts()).isEqualTo(1);
            assertThat(override.apiCallAttemptTimeout()).contains(Duration.ofSeconds(5));
            assertThat(override.apiCallTimeout()).contains(Duration.ofSeconds(10));
        }
    }

    @Test
    void leaseMustBeLongerThanApiCallTimeout() {
        assertThatThrownBy(() -> properties(10, 5, 10))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("lease duration");
    }

    private MeetingAnalysisPublisherProperties properties(
            long leaseSeconds,
            long attemptTimeoutSeconds,
            long callTimeoutSeconds
    ) {
        return new MeetingAnalysisPublisherProperties(
                true,
                1000,
                20,
                3,
                leaseSeconds,
                30,
                120,
                attemptTimeoutSeconds,
                callTimeoutSeconds,
                "https://sqs.ap-northeast-2.amazonaws.com/000000000000/staging",
                "ap-northeast-2"
        );
    }
}
