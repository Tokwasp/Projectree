package com.ssafy.projectree.domain.notification.dto;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.ssafy.projectree.domain.notification.entity.Notification;
import com.ssafy.projectree.domain.notification.entity.NotificationType;
import lombok.Builder;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
@JsonIgnoreProperties(ignoreUnknown = true)
public class NotificationMessage {

    private final int notificationId;
    private final NotificationType type;
    private final int receiverId;
    private final String message;
    private final LocalDateTime createdAt;

    @Builder
    @JsonCreator
    private NotificationMessage(
            @JsonProperty("notificationId") int notificationId,
            @JsonProperty("type") NotificationType type,
            @JsonProperty("receiverId") int receiverId,
            @JsonProperty("message") String message,
            @JsonProperty("createdAt") LocalDateTime createdAt) {
        this.notificationId = notificationId;
        this.type = type;
        this.receiverId = receiverId;
        this.message = message;
        this.createdAt = createdAt;
    }

    public static NotificationMessage from(Notification notification) {
        return NotificationMessage.builder()
                .notificationId(notification.getId())
                .type(notification.getType())
                .receiverId(notification.getReceiverId())
                .message(notification.getMessage())
                .createdAt(notification.getCreatedAt())
                .build();
    }
}
