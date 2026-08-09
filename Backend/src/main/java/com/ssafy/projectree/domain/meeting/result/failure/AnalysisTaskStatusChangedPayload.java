package com.ssafy.projectree.domain.meeting.result.failure;

public record AnalysisTaskStatusChangedPayload(
        AnalysisTaskType taskType,
        AnalysisTaskResultStatus status,
        String failureCode,
        String failureMessage
) {
}
