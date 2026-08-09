package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskCompletionResult;

public record GraphProjectionApplyResult(
        AnalysisTaskCompletionResult completionResult,
        boolean projectionUpdated,
        long requestedGraphVersion,
        long currentGraphVersion
) {
}
