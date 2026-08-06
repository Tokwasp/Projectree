package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphSnapshotReference;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayloadParser;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayloadValidator;
import com.ssafy.projectree.domain.meeting.result.graph.projection.AnalysisGraphProjectionApplier;
import com.ssafy.projectree.domain.meeting.result.graph.projection.GraphProjectionApplyResult;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.storage.GraphSnapshotLoader;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import tools.jackson.databind.json.JsonMapper;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class AnalysisGraphEventHandlerTest {

    @Mock private ProjectGraphChangedPayloadParser payloadParser;
    @Mock private ProjectGraphChangedPayloadValidator payloadValidator;
    @Mock private GraphSnapshotLoader snapshotLoader;
    @Mock private AnalysisGraphProjectionApplier projectionApplier;
    @Mock private ProjectGraphSnapshot snapshot;

    private AnalysisGraphEventHandler handler;

    @BeforeEach
    void setUp() {
        handler = new AnalysisGraphEventHandler(
                payloadParser, payloadValidator, snapshotLoader, projectionApplier
        );
    }

    @Test
    void loadsValidatedSnapshotOutsideApplierAndDelegatesIt() {
        AnalysisResultEventEnvelope event = event();
        ProjectGraphChangedPayload payload = payload();
        when(payloadParser.parse(event.payload())).thenReturn(payload);
        when(snapshotLoader.load(event, payload)).thenReturn(snapshot);
        when(snapshot.nodes()).thenReturn(List.of());
        when(snapshot.evidences()).thenReturn(List.of());
        when(projectionApplier.apply(event, payload, snapshot))
                .thenReturn(new GraphProjectionApplyResult(
                        com.ssafy.projectree.domain.meeting.entity.AnalysisTaskCompletionResult.APPLIED,
                        true,
                        1,
                        1
                ));

        handler.handle(event);

        verify(payloadValidator).validate(payload);
        verify(snapshotLoader).load(event, payload);
        verify(projectionApplier).apply(event, payload, snapshot);
    }

    @Test
    void doesNotInvokeApplierWhenSnapshotLoadingFails() {
        AnalysisResultEventEnvelope event = event();
        ProjectGraphChangedPayload payload = payload();
        when(payloadParser.parse(event.payload())).thenReturn(payload);
        doThrow(new IllegalStateException("snapshot unavailable"))
                .when(snapshotLoader).load(event, payload);

        org.assertj.core.api.Assertions.assertThatThrownBy(() -> handler.handle(event))
                .isInstanceOf(IllegalStateException.class);

        verify(projectionApplier, never()).apply(event, payload, snapshot);
    }

    @Test
    void supportsOnlyProjectGraphChangedEvents() {
        org.assertj.core.api.Assertions.assertThat(handler.supportedType())
                .isEqualTo(AnalysisResultEventType.PROJECT_GRAPH_CHANGED);
    }

    private AnalysisResultEventEnvelope event() {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.now(), 1, 2, UUID.randomUUID().toString(),
                JsonMapper.builder().build().createObjectNode()
        );
    }

    private ProjectGraphChangedPayload payload() {
        return new ProjectGraphChangedPayload(
                GraphResultSourceType.MEETING_ANALYSIS, 1,
                new GraphSnapshotReference("graph-bucket", "graph-snapshots/a.json", "application/json", 1,
                        "a".repeat(64))
        );
    }
}
