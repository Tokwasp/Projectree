package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayloadParser;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayloadValidator;
import com.ssafy.projectree.domain.meeting.result.graph.projection.AnalysisGraphProjectionApplier;
import com.ssafy.projectree.domain.meeting.result.graph.projection.GraphProjectionApplyResult;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.storage.GraphSnapshotLoader;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
@Slf4j
@RequiredArgsConstructor
@ConditionalOnBean(GraphSnapshotLoader.class)
public class AnalysisGraphEventHandler implements AnalysisResultEventHandler {

    private final ProjectGraphChangedPayloadParser payloadParser;
    private final ProjectGraphChangedPayloadValidator payloadValidator;
    private final GraphSnapshotLoader snapshotLoader;
    private final AnalysisGraphProjectionApplier projectionApplier;

    @Override
    public AnalysisResultEventType supportedType() {
        return AnalysisResultEventType.PROJECT_GRAPH_CHANGED;
    }

    @Override
    @Transactional(propagation = Propagation.NEVER)
    public void handle(AnalysisResultEventEnvelope event) {
        ProjectGraphChangedPayload payload = payloadParser.parse(event.payload());
        payloadValidator.validate(payload);
        ProjectGraphSnapshot snapshot = snapshotLoader.load(event, payload);
        GraphProjectionApplyResult result = projectionApplier.apply(event, payload, snapshot);
        log.info(
                "[AnalysisFlow] GRAPH_PROJECTION_APPLIED. eventId={}, commandId={}, projectId={}, meetingId={}, requestedGraphVersion={}, currentGraphVersion={}, projectionUpdated={}, completionResult={}, nodeCount={}, evidenceCount={}",
                event.eventId(),
                event.commandId(),
                event.projectId(),
                event.meetingId(),
                result.requestedGraphVersion(),
                result.currentGraphVersion(),
                result.projectionUpdated(),
                result.completionResult(),
                snapshot.nodes().size(),
                snapshot.evidences().size()
        );
    }
}
