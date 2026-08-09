package com.ssafy.projectree.domain.meeting.result.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Bindable;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;
import org.springframework.context.annotation.Configuration;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AnalysisResultConsumerPropertiesTest {

    private final ApplicationContextRunner contextRunner = new ApplicationContextRunner()
            .withUserConfiguration(PropertiesConfiguration.class);

    @Test
    void allowsBlankQueueUrlWhenDisabled() {
        AnalysisResultConsumerProperties properties = new AnalysisResultConsumerProperties(
                false, "", 20, 10, 1000, "ap-northeast-2"
        );

        assertThat(properties.queueUrl()).isBlank();
    }

    @Test
    void allowsEnabledConsumerWhenQueueUrlIsProvided() {
        AnalysisResultConsumerProperties properties = new AnalysisResultConsumerProperties(
                true, "https://example.invalid/result-queue", 20, 10, 1000, "ap-northeast-2"
        );

        assertThat(properties.enabled()).isTrue();
        assertThat(properties.queueUrl()).isEqualTo("https://example.invalid/result-queue");
    }

    @Test
    void bindsQueueUrlFromAwsAnalysisResultQueueUrlEnvironmentName() throws Exception {
        StandardEnvironment environment = new StandardEnvironment();
        environment.getPropertySources().addFirst(new MapPropertySource("test-environment", Map.of(
                "MEETING_ANALYSIS_RESULT_CONSUMER_ENABLED", "true",
                "AWS_ANALYSIS_RESULT_QUEUE_URL", "https://example.invalid/result-queue"
        )));
        new YamlPropertySourceLoader()
                .load("application", new ClassPathResource("application.yaml"))
                .forEach(source -> environment.getPropertySources().addLast(source));

        AnalysisResultConsumerProperties properties = Binder.get(environment)
                .bind("app.meeting-analysis.result-consumer", Bindable.of(AnalysisResultConsumerProperties.class))
                .orElseThrow(() -> new AssertionError("Result consumer properties must be bound"));

        assertThat(properties.enabled()).isTrue();
        assertThat(properties.queueUrl()).isEqualTo("https://example.invalid/result-queue");
    }

    @Test
    void rejectsInvalidEnabledConfigurationAndAwsRanges() {
        assertThatThrownBy(() -> new AnalysisResultConsumerProperties(
                true, "", 20, 10, 1000, "ap-northeast-2"
        )).isInstanceOf(IllegalArgumentException.class)
                .hasMessage("AWS_ANALYSIS_RESULT_QUEUE_URL is required when meeting analysis result consumer is enabled.");
        assertThatThrownBy(() -> new AnalysisResultConsumerProperties(
                false, "", 21, 10, 1000, "ap-northeast-2"
        )).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AnalysisResultConsumerProperties(
                false, "", 20, 11, 1000, "ap-northeast-2"
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void failsApplicationConfigurationWhenEnabledConsumerHasNoQueueUrl() {
        contextRunner.withPropertyValues(
                "app.meeting-analysis.result-consumer.enabled=true"
        ).run(context -> {
            assertThat(context.getStartupFailure()).isNotNull()
                    .hasRootCauseMessage(
                            "AWS_ANALYSIS_RESULT_QUEUE_URL is required when meeting analysis result consumer is enabled."
                    );
        });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(AnalysisResultConsumerProperties.class)
    static class PropertiesConfiguration {
    }
}
