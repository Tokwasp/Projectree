package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.dto.NotificationMessage;
import com.ssafy.projectree.domain.notification.entity.NotificationType;
import com.ssafy.projectree.global.config.notification.NotificationConfig;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.then;

@ExtendWith(MockitoExtension.class)
class NotificationPublisherTest {

    private static final LocalDateTime CREATED_AT = LocalDateTime.of(2026, 8, 4, 15, 21, 3);

    private final ObjectMapper objectMapper = JsonMapper.builder().build();

    @Mock
    private StringRedisTemplate stringRedisTemplate;

    private NotificationPublisher notificationPublisher;

    @BeforeEach
    void setUp() {
        notificationPublisher = new NotificationPublisher(stringRedisTemplate, objectMapper);
    }

    @DisplayName("알림은 모든 인스턴스가 구독하는 단일 토픽으로 발행된다.")
    @Test
    void publish() {
        // when
        notificationPublisher.publish(notificationMessage());

        // then
        ArgumentCaptor<String> topicCaptor = ArgumentCaptor.forClass(String.class);
        then(stringRedisTemplate).should().convertAndSend(topicCaptor.capture(), anyString());
        assertThat(topicCaptor.getValue()).isEqualTo(NotificationConfig.NOTIFICATION_TOPIC);
    }

    @DisplayName("발행한 페이로드는 다른 인스턴스에서 같은 알림으로 복원된다.")
    @Test
    void publishSendsRestorablePayload() {
        // given
        NotificationMessage message = notificationMessage();

        // when
        notificationPublisher.publish(message);

        // then
        NotificationMessage restored = objectMapper.readValue(publishedPayload(), NotificationMessage.class);
        assertThat(restored)
                .extracting(
                        NotificationMessage::getNotificationId,
                        NotificationMessage::getType,
                        NotificationMessage::getReceiverId,
                        NotificationMessage::getMessage,
                        NotificationMessage::getCreatedAt)
                .containsExactly(41, NotificationType.TREE_CREATED, 7,
                        NotificationType.TREE_CREATED.getMessage(), CREATED_AT);
    }

    @DisplayName("페이로드에 클래스 정보를 싣지 않아 두 서버의 패키지 구조에 묶이지 않는다.")
    @Test
    void publishSendsPlainJson() {
        // when
        notificationPublisher.publish(notificationMessage());

        // then
        assertThat(publishedPayload()).doesNotContain("@class");
    }

    private String publishedPayload() {
        ArgumentCaptor<String> payloadCaptor = ArgumentCaptor.forClass(String.class);
        then(stringRedisTemplate).should().convertAndSend(anyString(), payloadCaptor.capture());

        return payloadCaptor.getValue();
    }

    private NotificationMessage notificationMessage() {
        return NotificationMessage.builder()
                .notificationId(41)
                .type(NotificationType.TREE_CREATED)
                .receiverId(7)
                .message(NotificationType.TREE_CREATED.getMessage())
                .createdAt(CREATED_AT)
                .build();
    }
}
