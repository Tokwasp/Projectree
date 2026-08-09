package com.ssafy.projectree.domain.meeting.result.graph.event;

public record TreeCreatedNotificationEvent(
        int receiverId
) {

    public TreeCreatedNotificationEvent {
        if (receiverId <= 0) {
            throw new IllegalArgumentException("receiverId must be positive");
        }
    }
}
