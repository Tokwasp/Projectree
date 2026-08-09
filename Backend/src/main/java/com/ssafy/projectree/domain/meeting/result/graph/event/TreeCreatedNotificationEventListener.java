package com.ssafy.projectree.domain.meeting.result.graph.event;

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
public class TreeCreatedNotificationEventListener {

    private final NotificationService notificationService;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(TreeCreatedNotificationEvent event) {
        try {
            notificationService.createAndPublish(
                    NotificationType.TREE_CREATED,
                    event.receiverId()
            );
        } catch (RuntimeException exception) {
            log.error(
                    "Failed to send tree creation notification. receiverId={}",
                    event.receiverId(),
                    exception
            );
        }
    }
}
