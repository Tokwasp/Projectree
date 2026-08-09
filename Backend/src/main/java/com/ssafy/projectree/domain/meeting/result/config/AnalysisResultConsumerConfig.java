package com.ssafy.projectree.domain.meeting.result.config;

import com.ssafy.projectree.domain.meeting.result.consumer.AnalysisResultSqsGateway;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultEventProcessor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sqs.SqsClient;

import java.time.Duration;

@Configuration
@EnableConfigurationProperties(AnalysisResultConsumerProperties.class)
public class AnalysisResultConsumerConfig {

    @Bean(destroyMethod = "close")
    @ConditionalOnBean(AnalysisResultEventProcessor.class)
    @ConditionalOnProperty(
            prefix = "app.meeting-analysis.result-consumer",
            name = "enabled",
            havingValue = "true"
    )
    AnalysisResultSqsGateway analysisResultSqsGateway(
            AnalysisResultConsumerProperties properties
    ) {
        Duration attemptTimeout = Duration.ofSeconds(properties.waitTimeSeconds() + 5);
        SqsClient sqsClient = SqsClient.builder()
                .region(Region.of(properties.region()))
                .credentialsProvider(DefaultCredentialsProvider.builder().build())
                .overrideConfiguration(configuration -> configuration
                        .retryStrategy(strategy -> strategy.maxAttempts(1))
                        .apiCallAttemptTimeout(attemptTimeout)
                        .apiCallTimeout(attemptTimeout.plusSeconds(5)))
                .build();
        return new AnalysisResultSqsGateway(sqsClient, properties);
    }
}
