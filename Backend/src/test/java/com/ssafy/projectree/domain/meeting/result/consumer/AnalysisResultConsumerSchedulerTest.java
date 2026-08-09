package com.ssafy.projectree.domain.meeting.result.consumer;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class AnalysisResultConsumerSchedulerTest {

    @Mock private AnalysisResultConsumer consumer;

    @Test
    void delegatesScheduledExecutionToConsumer() {
        AnalysisResultConsumerScheduler scheduler = new AnalysisResultConsumerScheduler(consumer);

        scheduler.consumeAnalysisResults();

        verify(consumer).consumeAvailable();
    }
}
