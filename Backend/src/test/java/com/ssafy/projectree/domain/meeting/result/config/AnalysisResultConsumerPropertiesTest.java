package com.ssafy.projectree.domain.meeting.result.config;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AnalysisResultConsumerPropertiesTest {

    @Test
    void allowsBlankQueueUrlWhenDisabled() {
        AnalysisResultConsumerProperties properties = new AnalysisResultConsumerProperties(
                false, "", 20, 10, 1000, "ap-northeast-2"
        );

        assertThat(properties.queueUrl()).isBlank();
    }

    @Test
    void rejectsInvalidEnabledConfigurationAndAwsRanges() {
        assertThatThrownBy(() -> new AnalysisResultConsumerProperties(
                true, "", 20, 10, 1000, "ap-northeast-2"
        )).isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("queue URL");
        assertThatThrownBy(() -> new AnalysisResultConsumerProperties(
                false, "", 21, 10, 1000, "ap-northeast-2"
        )).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> new AnalysisResultConsumerProperties(
                false, "", 20, 11, 1000, "ap-northeast-2"
        )).isInstanceOf(IllegalArgumentException.class);
    }
}
