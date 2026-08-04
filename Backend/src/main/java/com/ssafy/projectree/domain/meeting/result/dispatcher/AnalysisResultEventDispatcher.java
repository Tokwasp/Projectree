package com.ssafy.projectree.domain.meeting.result.dispatcher;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultHandlerUnavailableException;
import com.ssafy.projectree.domain.meeting.result.handler.AnalysisResultEventHandler;
import jakarta.annotation.PostConstruct;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;

@Component
@RequiredArgsConstructor
public class AnalysisResultEventDispatcher {

    private final List<AnalysisResultEventHandler> handlers;
    private final Map<AnalysisResultEventType, AnalysisResultEventHandler> handlersByType =
            new EnumMap<>(AnalysisResultEventType.class);

    @PostConstruct
    void initializeHandlers() {
        for (AnalysisResultEventHandler handler : handlers) {
            AnalysisResultEventHandler previous = handlersByType.putIfAbsent(
                    handler.supportedType(), handler
            );
            if (previous != null) {
                throw new IllegalStateException(
                        "Multiple analysis result handlers are registered for "
                                + handler.supportedType()
                );
            }
        }
    }

    public void dispatch(AnalysisResultEventEnvelope event) {
        AnalysisResultEventHandler handler = handlersByType.get(event.eventType());
        if (handler == null) {
            throw new AnalysisResultHandlerUnavailableException(
                    "No analysis result handler is registered for " + event.eventType()
            );
        }
        handler.handle(event);
    }
}
