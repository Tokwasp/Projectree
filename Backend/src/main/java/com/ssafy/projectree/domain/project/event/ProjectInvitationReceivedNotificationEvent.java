package com.ssafy.projectree.domain.project.event;

public record ProjectInvitationReceivedNotificationEvent(
        int receiverId
) {

    public ProjectInvitationReceivedNotificationEvent {
        if (receiverId <= 0) {
            throw new IllegalArgumentException("receiverId must be positive");
        }
    }
}
