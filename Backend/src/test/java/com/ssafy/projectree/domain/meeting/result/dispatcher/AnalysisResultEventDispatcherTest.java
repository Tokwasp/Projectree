package com.ssafy.projectree.domain.meeting.result.dispatcher;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultHandlerUnavailableException;
import com.ssafy.projectree.domain.meeting.result.handler.AnalysisResultEventHandler;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AnalysisResultEventDispatcherTest {

    @Test
    void dispatchesOnlyRegisteredTypeAndRejectsUnavailableTypes() {
        RecordingHandler handler = new RecordingHandler(AnalysisResultEventType.ANALYSIS_TASK_STATUS_CHANGED);
        AnalysisResultEventDispatcher dispatcher = new AnalysisResultEventDispatcher(List.of(handler));
        dispatcher.initializeHandlers();

        dispatcher.dispatch(event(AnalysisResultEventType.ANALYSIS_TASK_STATUS_CHANGED));

        assertThat(handler.calls).isEqualTo(1);
        assertThatThrownBy(() -> dispatcher.dispatch(event(AnalysisResultEventType.MEETING_SUMMARY_READY)))
                .isInstanceOf(AnalysisResultHandlerUnavailableException.class);
        assertThatThrownBy(() -> dispatcher.dispatch(event(AnalysisResultEventType.PROJECT_GRAPH_CHANGED)))
                .isInstanceOf(AnalysisResultHandlerUnavailableException.class);
    }

    @Test
    void duplicateHandlersForSameTypeFailAtStartup() {
        AnalysisResultEventDispatcher dispatcher = new AnalysisResultEventDispatcher(List.of(
                new RecordingHandler(AnalysisResultEventType.ANALYSIS_TASK_STATUS_CHANGED),
                new RecordingHandler(AnalysisResultEventType.ANALYSIS_TASK_STATUS_CHANGED)
        ));

        assertThatThrownBy(dispatcher::initializeHandlers)
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("Multiple analysis result handlers");
    }

    private AnalysisResultEventEnvelope event(AnalysisResultEventType eventType) {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), eventType, Instant.now(), 1, 1,
                UUID.randomUUID().toString(), JsonMapper.builder().build().createObjectNode()
        );
    }

    private static class RecordingHandler implements AnalysisResultEventHandler {
        private final AnalysisResultEventType type;
        private int calls;

        private RecordingHandler(AnalysisResultEventType type) {
            this.type = type;
        }

        @Override
        public AnalysisResultEventType supportedType() {
            return type;
        }

        @Override
        public void handle(AnalysisResultEventEnvelope event) {
            calls++;
        }
    }
}
