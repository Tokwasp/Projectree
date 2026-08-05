package com.ssafy.projectree.domain.meeting.result.failure;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import org.springframework.stereotype.Component;

@Component
public class AnalysisTaskStatusChangedPayloadValidator {

    private static final int MAX_FAILURE_CODE_LENGTH = 100;
    private static final int MAX_FAILURE_MESSAGE_LENGTH = 1000;

    public void validate(AnalysisTaskStatusChangedPayload payload) {
        if (payload == null || payload.taskType() == null) {
            throw new AnalysisResultContractException("Analysis task type must not be null");
        }
        if (payload.status() != AnalysisTaskResultStatus.FAILED) {
            throw new AnalysisResultContractException("Analysis task result status must be FAILED");
        }
        validateText(payload.failureCode(), "failureCode", MAX_FAILURE_CODE_LENGTH);
        validateText(payload.failureMessage(), "failureMessage", MAX_FAILURE_MESSAGE_LENGTH);
    }

    private void validateText(String value, String fieldName, int maxLength) {
        if (value == null || value.isBlank()) {
            throw new AnalysisResultContractException(fieldName + " must not be blank");
        }
        if (value.length() > maxLength) {
            throw new AnalysisResultContractException(fieldName + " exceeds maximum length");
        }
    }
}
