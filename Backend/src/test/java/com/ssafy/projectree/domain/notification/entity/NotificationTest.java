package com.ssafy.projectree.domain.notification.entity;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class NotificationTest {

    @DisplayName("알림은 타입과 수신자를 그대로 보관한다.")
    @Test
    void of() {
        // when
        Notification notification = Notification.of(NotificationType.TREE_CREATED, 7);

        // then
        assertThat(notification.getType()).isEqualTo(NotificationType.TREE_CREATED);
        assertThat(notification.getReceiverId()).isEqualTo(7);
    }

    @DisplayName("알림 문구는 저장하지 않고 타입이 들고 있는 문구를 그대로 사용한다.")
    @Test
    void getMessage() {
        // given
        Notification notification = Notification.of(NotificationType.MEETING_RECORD_CREATED, 7);

        // when
        String message = notification.getMessage();

        // then
        assertThat(message).isEqualTo(NotificationType.MEETING_RECORD_CREATED.getMessage());
    }

    @DisplayName("모든 알림 타입은 사용자에게 보여 줄 문구를 갖는다.")
    @Test
    void everyTypeHasMessage() {
        // when // then
        assertThat(NotificationType.values())
                .allSatisfy(type -> assertThat(type.getMessage()).isNotBlank());
    }
}
