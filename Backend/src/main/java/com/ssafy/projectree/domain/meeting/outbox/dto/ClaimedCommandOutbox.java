package com.ssafy.projectree.domain.meeting.outbox.dto;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;

public record ClaimedCommandOutbox(
        int outboxId,
        String commandId,
        MeetingAnalysisCommandType commandType,
        String payload,
        String claimToken,
        int attemptCount
) {

    public ClaimedCommandOutbox(
            int outboxId,
            String commandId,
            String payload,
            String claimToken,
            int attemptCount
    ) {
        this(
                outboxId,
                commandId,
                MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                payload,
                claimToken,
                attemptCount
        );
    }
}
