package com.ssafy.projectree.domain.meeting.outbox.config;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

import java.time.Clock;
import java.time.Duration;
import java.time.ZoneId;

@Configuration
@EnableConfigurationProperties(MeetingAnalysisPublisherProperties.class)
public class MeetingAnalysisPublisherConfig {

    @Bean
    @ConditionalOnMissingBean
    Clock meetingAnalysisClock() {
        return Clock.system(ZoneId.of("Asia/Seoul"));
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "app.meeting-analysis.publisher",
            name = "enabled",
            havingValue = "true"
    )
    SqsClient meetingAnalysisSqsClient(MeetingAnalysisPublisherProperties properties) {
        if (properties.queueUrl().isBlank()) {
            throw new IllegalStateException("Meeting analysis command queue URL is required");
        }
        return SqsClient.builder()
                .region(Region.of(properties.region()))
                .credentialsProvider(DefaultCredentialsProvider.builder().build())
                .overrideConfiguration(configuration -> configuration
                        .retryStrategy(strategy -> strategy.maxAttempts(1))
                        .apiCallAttemptTimeout(Duration.ofSeconds(
                                properties.apiCallAttemptTimeoutSeconds()
                        ))
                        .apiCallTimeout(Duration.ofSeconds(properties.apiCallTimeoutSeconds())))
                .build();
    }
}
