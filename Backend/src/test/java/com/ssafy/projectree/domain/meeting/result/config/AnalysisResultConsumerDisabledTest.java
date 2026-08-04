package com.ssafy.projectree.domain.meeting.result.config;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.consumer.AnalysisResultConsumer;
import com.ssafy.projectree.domain.meeting.result.consumer.AnalysisResultConsumerScheduler;
import com.ssafy.projectree.domain.meeting.result.consumer.AnalysisResultSqsGateway;
import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultEventProcessor;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

class AnalysisResultConsumerDisabledTest extends IntegrationTestSupport {

    @Autowired
    private ApplicationContext applicationContext;

    @Test
    void defaultDisabledConfigurationCreatesNoPollingDespiteDefaultProcessorBean() {
        assertThat(applicationContext.getBeansOfType(AnalysisResultSqsGateway.class)).isEmpty();
        assertThat(applicationContext.getBeansOfType(AnalysisResultConsumer.class)).isEmpty();
        assertThat(applicationContext.getBeansOfType(AnalysisResultConsumerScheduler.class)).isEmpty();
        assertThat(applicationContext.getBeansOfType(AnalysisResultEventProcessor.class)).hasSize(1);
    }
}
