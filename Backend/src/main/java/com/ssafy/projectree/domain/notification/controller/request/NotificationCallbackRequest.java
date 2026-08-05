package com.ssafy.projectree.domain.notification.controller.request;

import com.ssafy.projectree.domain.notification.entity.Notification;
import com.ssafy.projectree.domain.notification.entity.NotificationType;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import lombok.Builder;
import lombok.Getter;

@Getter
public class NotificationCallbackRequest {

    @NotNull(message = "알림 타입은 필수입니다.")
    private NotificationType type;

    @Positive(message = "수신자 id는 양수여야 합니다.")
    private int receiverId;

    @Builder
    private NotificationCallbackRequest(NotificationType type, int receiverId) {
        this.type = type;
        this.receiverId = receiverId;
    }

    private NotificationCallbackRequest() {
    }

    public Notification toEntity() {
        return Notification.of(type, receiverId);
    }
}
