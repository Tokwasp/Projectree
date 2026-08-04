package com.ssafy.projectree.domain.meeting.result.consumer;

import com.ssafy.projectree.domain.meeting.result.processor.AnalysisResultEventProcessor;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
@ConditionalOnBean(AnalysisResultEventProcessor.class)
@ConditionalOnProperty(
        prefix = "app.meeting-analysis.result-consumer",
        name = "enabled",
        havingValue = "true"
)
public class AnalysisResultConsumerScheduler {

    private final AnalysisResultConsumer analysisResultConsumer;

    @Scheduled(fixedDelayString = "${app.meeting-analysis.result-consumer.polling-delay-ms:1000}")
    public void consumeAnalysisResults() {
        analysisResultConsumer.consumeAvailable();
    }
}
