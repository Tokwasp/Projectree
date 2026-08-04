package com.ssafy.projectree.domain.meeting.service;

public enum MeetingSynchronizationOutcome {
    CREATED,
    ALREADY_EXISTS,
    CREATOR_REGISTERED,
    CREATOR_PROJECT_MEMBER_NOT_FOUND,
    CREATOR_CONFLICT,
    UNIQUE_COLLISION,
    PROJECT_NOT_FOUND,
    INVALID_ENTRY
}
