package com.ssafy.projectree.domain.meeting.result.exception;

public class InvalidAnalysisTaskStateException extends AnalysisResultContractException {

    public InvalidAnalysisTaskStateException(String message, Throwable cause) {
        super(message, cause);
    }
}
