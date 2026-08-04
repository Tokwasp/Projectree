package com.ssafy.projectree.domain.meeting.dto.request;

import jakarta.validation.constraints.NotNull;

public record MeetingAnalysisRequest(
        @NotNull Boolean generateSummary,
        @NotNull Boolean generateNodes
) {
}
