package com.ssafy.projectree.domain.meeting.record.event;

public record MeetingRecordCreatedNotificationEvent(
        int receiverId
) {

    public MeetingRecordCreatedNotificationEvent {
        if (receiverId <= 0) {
            throw new IllegalArgumentException("receiverId must be positive");
        }
    }
}
