package com.ssafy.projectree.domain.meeting.outbox.service;

public enum CommandPublishFailureOutcome {
    STALE,
    RETRY_SCHEDULED,
    FINAL_FAILED
}
