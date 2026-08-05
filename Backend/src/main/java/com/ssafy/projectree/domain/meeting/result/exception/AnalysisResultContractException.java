package com.ssafy.projectree.domain.meeting.result.exception;

public class AnalysisResultContractException extends RuntimeException {

    public AnalysisResultContractException(String message) {
        super(message);
    }

    public AnalysisResultContractException(String message, Throwable cause) {
        super(message, cause);
    }
}
