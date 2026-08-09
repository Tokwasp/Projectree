package com.ssafy.projectree.domain.project.event;

import com.ssafy.projectree.domain.notification.entity.NotificationType;
import com.ssafy.projectree.domain.notification.service.NotificationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Slf4j
@Component
@RequiredArgsConstructor
public class ProjectInvitationReceivedNotificationEventListener {

    private final NotificationService notificationService;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(ProjectInvitationReceivedNotificationEvent event) {
        try {
            notificationService.createAndPublish(
                    NotificationType.PROJECT_INVITATION_RECEIVED,
                    event.receiverId()
            );
        } catch (RuntimeException exception) {
            log.error(
                    "프로젝트 초대 알림 전송에 실패했습니다. receiverId={}",
                    event.receiverId(),
                    exception
            );
        }
    }
}
