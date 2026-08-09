package com.ssafy.projectree.domain.meeting.record.event;

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
public class MeetingRecordCreatedNotificationEventListener {

    private final NotificationService notificationService;

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void handle(MeetingRecordCreatedNotificationEvent event) {
        try {
            notificationService.createAndPublish(
                    NotificationType.MEETING_RECORD_CREATED,
                    event.receiverId()
            );
        } catch (RuntimeException exception) {
            log.error(
                    "회의록 생성 완료 알림 전송에 실패했다. receiverId={}",
                    event.receiverId(),
                    exception
            );
        }
    }
}
