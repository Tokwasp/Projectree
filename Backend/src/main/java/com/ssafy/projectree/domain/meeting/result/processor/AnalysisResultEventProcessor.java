package com.ssafy.projectree.domain.meeting.result.processor;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;

public interface AnalysisResultEventProcessor {

    AnalysisResultProcessingOutcome process(AnalysisResultEventEnvelope event);
}
