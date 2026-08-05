package com.ssafy.projectree.domain.meeting.result.consumer;

import com.ssafy.projectree.domain.meeting.result.config.AnalysisResultConsumerProperties;
import com.ssafy.projectree.domain.meeting.result.dispatcher.AnalysisResultEventDispatcher;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.graph.config.GraphSnapshotProperties;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
@ConditionalOnProperty(
        prefix = "app.meeting-analysis.result-consumer",
        name = "enabled",
        havingValue = "true"
)
public class AnalysisResultConsumerReadinessValidator {

    private final AnalysisResultConsumerProperties consumerProperties;
    private final GraphSnapshotProperties graphSnapshotProperties;
    private final AnalysisResultEventDispatcher dispatcher;

    @PostConstruct
    void validate() {
        if (!consumerProperties.enabled()) {
            return;
        }
        if (!graphSnapshotProperties.s3().enabled()) {
            throw new IllegalStateException(
                    "Analysis result consumer requires graph snapshot S3 to be enabled"
            );
        }
        for (AnalysisResultEventType eventType : AnalysisResultEventType.values()) {
            if (!dispatcher.supports(eventType)) {
                throw new IllegalStateException(
                        "Analysis result consumer requires handler for " + eventType
                );
            }
        }
    }
}
