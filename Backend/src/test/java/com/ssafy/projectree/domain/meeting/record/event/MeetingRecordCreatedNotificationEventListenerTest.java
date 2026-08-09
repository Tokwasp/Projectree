package com.ssafy.projectree.domain.meeting.record.event;

import com.ssafy.projectree.domain.notification.entity.NotificationType;
import com.ssafy.projectree.domain.notification.service.NotificationService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class MeetingRecordCreatedNotificationEventListenerTest {

    private final NotificationService notificationService =
            mock(NotificationService.class);
    private final MeetingRecordCreatedNotificationEventListener listener =
            new MeetingRecordCreatedNotificationEventListener(notificationService);

    @DisplayName("회의록 생성 완료 이벤트는 기존 NotificationService로 전달한다.")
    @Test
    void delegatesToNotificationService() {
        MeetingRecordCreatedNotificationEvent event =
                new MeetingRecordCreatedNotificationEvent(22);

        listener.handle(event);

        verify(notificationService).createAndPublish(
                NotificationType.MEETING_RECORD_CREATED,
                22
        );
    }

    @DisplayName("알림 처리 실패는 Listener 밖으로 전파하지 않는다.")
    @Test
    void swallowsNotificationFailure() {
        MeetingRecordCreatedNotificationEvent event =
                new MeetingRecordCreatedNotificationEvent(22);
        doThrow(new RuntimeException("publish failed"))
                .when(notificationService)
                .createAndPublish(NotificationType.MEETING_RECORD_CREATED, 22);

        assertThatCode(() -> listener.handle(event))
                .doesNotThrowAnyException();
    }
}
