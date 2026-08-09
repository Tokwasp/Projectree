package com.ssafy.projectree.domain.meeting.result.exception;

public class AnalysisResultRetryableException extends RuntimeException {

    public AnalysisResultRetryableException(String message, Throwable cause) {
        super(message, cause);
    }
}
