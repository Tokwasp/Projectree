package com.ssafy.projectree.domain.meeting.result.exception;

public class DuplicateAnalysisResultEventException extends RuntimeException {

    public DuplicateAnalysisResultEventException(String eventId, Throwable cause) {
        super("Analysis result event is already processed. eventId=" + eventId, cause);
    }
}
