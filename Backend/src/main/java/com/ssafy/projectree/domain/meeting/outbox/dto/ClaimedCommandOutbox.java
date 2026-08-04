package com.ssafy.projectree.domain.meeting.outbox.dto;

public record ClaimedCommandOutbox(
        int outboxId,
        String commandId,
        String payload,
        String claimToken,
        int attemptCount
) {
}
