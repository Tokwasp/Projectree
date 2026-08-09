package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;

public interface AnalysisResultEventHandler {

    AnalysisResultEventType supportedType();

    void handle(AnalysisResultEventEnvelope event);
}
