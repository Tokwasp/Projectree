package com.ssafy.projectree.domain.meeting.result.graph.event;

import com.ssafy.projectree.domain.notification.entity.NotificationType;
import com.ssafy.projectree.domain.notification.service.NotificationService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class TreeCreatedNotificationEventListenerTest {

    private final NotificationService notificationService =
            mock(NotificationService.class);
    private final TreeCreatedNotificationEventListener listener =
            new TreeCreatedNotificationEventListener(notificationService);

    @DisplayName("트리 생성 완료 이벤트를 TREE_CREATED 알림으로 전달한다.")
    @Test
    void delegatesToNotificationService() {
        TreeCreatedNotificationEvent event = new TreeCreatedNotificationEvent(22);

        listener.handle(event);

        verify(notificationService).createAndPublish(
                NotificationType.TREE_CREATED,
                22
        );
    }

    @DisplayName("알림 처리 실패를 Listener 밖으로 전파하지 않는다.")
    @Test
    void swallowsNotificationFailure() {
        TreeCreatedNotificationEvent event = new TreeCreatedNotificationEvent(22);
        doThrow(new RuntimeException("publish failed"))
                .when(notificationService)
                .createAndPublish(NotificationType.TREE_CREATED, 22);

        assertThatCode(() -> listener.handle(event))
                .doesNotThrowAnyException();
    }
}
