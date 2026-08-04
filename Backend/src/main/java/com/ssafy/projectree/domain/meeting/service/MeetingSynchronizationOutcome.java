package com.ssafy.projectree.domain.meeting.service;

public enum MeetingSynchronizationOutcome {
    CREATED,
    ALREADY_EXISTS,
    UNIQUE_COLLISION,
    PROJECT_NOT_FOUND,
    INVALID_ENTRY
}
