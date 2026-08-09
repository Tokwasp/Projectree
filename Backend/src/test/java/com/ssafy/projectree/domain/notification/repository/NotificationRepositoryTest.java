package com.ssafy.projectree.domain.notification.repository;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.notification.entity.Notification;
import com.ssafy.projectree.domain.notification.entity.NotificationType;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class NotificationRepositoryTest extends IntegrationTestSupport {

    private static final int RECEIVER_ID = 7;
    private static final int OTHER_RECEIVER_ID = 8;

    @Autowired
    private NotificationRepository notificationRepository;

    @DisplayName("마지막으로 받은 알림 이후에 쌓인 알림만 id 오름차순으로 조회한다.")
    @Test
    void findNotReceivedMessages() {
        // given
        Notification received = save(RECEIVER_ID, NotificationType.TREE_CREATED);
        Notification missedFirst = save(RECEIVER_ID, NotificationType.MEETING_RECORD_CREATED);
        Notification missedSecond = save(RECEIVER_ID, NotificationType.TREE_CREATED);

        // when
        List<Notification> notifications =
                notificationRepository.findNotReceivedMessages(RECEIVER_ID, received.getId());

        // then
        assertThat(notifications).hasSize(2)
                .extracting(Notification::getId)
                .containsExactly(missedFirst.getId(), missedSecond.getId());
    }

    @DisplayName("마지막으로 받은 알림 이후의 알림을 조회할 때 다른 회원의 알림은 섞이지 않는다.")
    @Test
    void findNotReceivedMessagesExcludesOtherReceiver() {
        // given
        Notification received = save(RECEIVER_ID, NotificationType.TREE_CREATED);
        Notification missed = save(RECEIVER_ID, NotificationType.TREE_CREATED);
        save(OTHER_RECEIVER_ID, NotificationType.TREE_CREATED);

        // when
        List<Notification> notifications =
                notificationRepository.findNotReceivedMessages(RECEIVER_ID, received.getId());

        // then
        assertThat(notifications).hasSize(1)
                .extracting(Notification::getId)
                .containsExactly(missed.getId());
    }

    @DisplayName("마지막으로 받은 알림 이후에 쌓인 알림이 없으면 빈 목록을 반환한다.")
    @Test
    void findNotReceivedMessagesWhenNothingMissed() {
        // given
        Notification received = save(RECEIVER_ID, NotificationType.TREE_CREATED);

        // when
        List<Notification> notifications =
                notificationRepository.findNotReceivedMessages(RECEIVER_ID, received.getId());

        // then
        assertThat(notifications).isEmpty();
    }

    private Notification save(int receiverId, NotificationType type) {
        return notificationRepository.saveAndFlush(Notification.of(type, receiverId));
    }
}
