package com.ssafy.projectree.domain.project.event;

import com.ssafy.projectree.domain.notification.entity.NotificationType;
import com.ssafy.projectree.domain.notification.service.NotificationService;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

class ProjectInvitationReceivedNotificationEventListenerTest {

    private final NotificationService notificationService =
            mock(NotificationService.class);
    private final ProjectInvitationReceivedNotificationEventListener listener =
            new ProjectInvitationReceivedNotificationEventListener(notificationService);

    @Test
    void delegatesInvitationNotificationToExistingNotificationService() {
        ProjectInvitationReceivedNotificationEvent event =
                new ProjectInvitationReceivedNotificationEvent(22);

        listener.handle(event);

        verify(notificationService).createAndPublish(
                NotificationType.PROJECT_INVITATION_RECEIVED,
                22
        );
        assertThat(NotificationType.PROJECT_INVITATION_RECEIVED.getMessage())
                .isEqualTo("프로젝트 초대가 도착했어요. 메일을 확인해 주세요.");
    }

    @Test
    void isolatesInvitationFlowFromNotificationFailure() {
        ProjectInvitationReceivedNotificationEvent event =
                new ProjectInvitationReceivedNotificationEvent(22);
        doThrow(new RuntimeException("publish failed"))
                .when(notificationService)
                .createAndPublish(NotificationType.PROJECT_INVITATION_RECEIVED, 22);

        assertThatCode(() -> listener.handle(event))
                .doesNotThrowAnyException();
    }
}
