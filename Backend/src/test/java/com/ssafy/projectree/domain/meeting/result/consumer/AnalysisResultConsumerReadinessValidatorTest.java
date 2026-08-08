package com.ssafy.projectree.domain.meeting.result.consumer;

import com.ssafy.projectree.domain.meeting.result.config.AnalysisResultConsumerProperties;
import com.ssafy.projectree.domain.meeting.result.dispatcher.AnalysisResultEventDispatcher;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.graph.config.GraphSnapshotProperties;
import com.ssafy.projectree.domain.meeting.result.handler.AnalysisResultEventHandler;
import org.junit.jupiter.api.Test;

import java.util.Arrays;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AnalysisResultConsumerReadinessValidatorTest {

    @Test
    void rejectsEnabledConsumerWhenGraphSnapshotS3IsDisabled() {
        AnalysisResultConsumerReadinessValidator validator = new AnalysisResultConsumerReadinessValidator(
                enabledConsumerProperties(),
                new GraphSnapshotProperties(1024,
                        new GraphSnapshotProperties.S3(false, "", "graph-snapshots/", "", "")),
                dispatcherWithAllHandlers()
        );

        assertThatThrownBy(validator::validate)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("graph snapshot S3");
    }

    @Test
    void rejectsEnabledConsumerWhenAnyResultHandlerIsMissing() {
        AnalysisResultEventDispatcher dispatcher = new AnalysisResultEventDispatcher(
                java.util.List.of(new RecordingHandler(AnalysisResultEventType.MEETING_SUMMARY_READY))
        );
        dispatcher.initializeHandlers();
        AnalysisResultConsumerReadinessValidator validator = new AnalysisResultConsumerReadinessValidator(
                enabledConsumerProperties(), enabledGraphSnapshotProperties(), dispatcher
        );

        assertThatThrownBy(validator::validate)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("requires handler");
    }

    @Test
    void acceptsEnabledConsumerWhenAllImplementedResultHandlersAndGraphS3AreAvailable() {
        AnalysisResultConsumerReadinessValidator validator = new AnalysisResultConsumerReadinessValidator(
                enabledConsumerProperties(),
                enabledGraphSnapshotProperties(),
                dispatcherWithImplementedHandlers()
        );

        assertThatCode(validator::validate).doesNotThrowAnyException();
    }

    private AnalysisResultConsumerProperties enabledConsumerProperties() {
        return new AnalysisResultConsumerProperties(true, "queue-url", 1, 1, 1000, "ap-northeast-2");
    }

    private GraphSnapshotProperties enabledGraphSnapshotProperties() {
        return new GraphSnapshotProperties(1024,
                new GraphSnapshotProperties.S3(true, "graph-bucket", "graph-snapshots/", "ap-northeast-2", ""));
    }

    private AnalysisResultEventDispatcher dispatcherWithAllHandlers() {
        List<AnalysisResultEventHandler> handlers = Arrays.stream(AnalysisResultEventType.values())
                .<AnalysisResultEventHandler>map(RecordingHandler::new)
                .toList();
        AnalysisResultEventDispatcher dispatcher = new AnalysisResultEventDispatcher(handlers);
        dispatcher.initializeHandlers();
        return dispatcher;
    }

    private AnalysisResultEventDispatcher dispatcherWithImplementedHandlers() {
        List<AnalysisResultEventHandler> handlers = List.of(
                new RecordingHandler(AnalysisResultEventType.MEETING_SUMMARY_READY),
                new RecordingHandler(AnalysisResultEventType.PROJECT_GRAPH_CHANGED),
                new RecordingHandler(AnalysisResultEventType.ANALYSIS_TASK_STATUS_CHANGED),
                new RecordingHandler(AnalysisResultEventType.NODE_DELETE_REJECTED)
        );
        AnalysisResultEventDispatcher dispatcher = new AnalysisResultEventDispatcher(handlers);
        dispatcher.initializeHandlers();
        return dispatcher;
    }

    private record RecordingHandler(AnalysisResultEventType supportedType) implements AnalysisResultEventHandler {
        @Override
        public void handle(AnalysisResultEventEnvelope event) {
        }
    }
}
