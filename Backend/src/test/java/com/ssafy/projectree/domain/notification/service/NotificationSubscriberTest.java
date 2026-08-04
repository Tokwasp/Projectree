package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.dto.NotificationMessage;
import com.ssafy.projectree.domain.notification.entity.NotificationType;
import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.connection.DefaultMessage;
import org.springframework.data.redis.connection.Message;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.json.JsonMapper;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.never;

@ExtendWith(MockitoExtension.class)
class NotificationSubscriberTest {

    private static final int RECEIVER_ID = 7;
    private static final String TOPIC = "NOTIFICATION";

    private final ObjectMapper objectMapper = JsonMapper.builder().build();
    private final EmitterRepository emitterRepository = new EmitterRepository();

    @Mock
    private NotificationSender notificationSender;

    private NotificationSubscriber notificationSubscriber;

    @BeforeEach
    void setUp() {
        notificationSubscriber = new NotificationSubscriber(objectMapper, emitterRepository, notificationSender);
    }

    @DisplayName("수신자가 탭을 두 개 열어 두었으면 두 연결 모두에 같은 알림을 보낸다.")
    @Test
    void onMessage() {
        // given
        emitterRepository.save("7_1000", new SseEmitter());
        emitterRepository.save("7_2000", new SseEmitter());

        // when
        notificationSubscriber.onMessage(message(notificationMessage(41)), null);

        // then
        then(notificationSender).should().send(
                eq("7_1000"), any(SseEmitter.class), eq("41"),
                eq(NotificationSender.NOTIFICATION_EVENT), any(NotificationMessage.class));
        then(notificationSender).should().send(
                eq("7_2000"), any(SseEmitter.class), eq("41"),
                eq(NotificationSender.NOTIFICATION_EVENT), any(NotificationMessage.class));
    }

    @DisplayName("이 인스턴스에 붙어 있는 다른 회원의 연결로는 알림이 나가지 않는다.")
    @Test
    void onMessageDoesNotSendToOtherMember() {
        // given
        emitterRepository.save("7_1000", new SseEmitter());
        emitterRepository.save("8_1000", new SseEmitter());

        // when
        notificationSubscriber.onMessage(message(notificationMessage(41)), null);

        // then
        then(notificationSender).should().send(
                eq("7_1000"), any(SseEmitter.class), anyString(), anyString(), any());
        then(notificationSender).should(never()).send(
                eq("8_1000"), any(SseEmitter.class), anyString(), anyString(), any());
    }

    @DisplayName("수신자가 다른 인스턴스에 붙어 있어 내 메모리에 연결이 없으면 아무것도 하지 않는다.")
    @Test
    void onMessageWhenReceiverIsNotOnThisInstance() {
        // when // then
        assertThatCode(() -> notificationSubscriber.onMessage(message(notificationMessage(41)), null))
                .doesNotThrowAnyException();

        then(notificationSender).shouldHaveNoInteractions();
    }

    @DisplayName("전달받은 알림 내용이 그대로 SSE 데이터로 나간다.")
    @Test
    void onMessageDeliversPayloadAsIs() {
        // given
        emitterRepository.save("7_1000", new SseEmitter());
        NotificationMessage published = notificationMessage(41);

        // when
        notificationSubscriber.onMessage(message(published), null);

        // then
        ArgumentCaptor<NotificationMessage> captor = ArgumentCaptor.forClass(NotificationMessage.class);
        then(notificationSender).should().send(anyString(), any(SseEmitter.class), anyString(), anyString(),
                captor.capture());
        assertThat(captor.getValue())
                .extracting(
                        NotificationMessage::getNotificationId,
                        NotificationMessage::getType,
                        NotificationMessage::getReceiverId,
                        NotificationMessage::getMessage)
                .containsExactly(41, NotificationType.TREE_CREATED, RECEIVER_ID,
                        NotificationType.TREE_CREATED.getMessage());
    }

    @DisplayName("메시지 한 건의 처리 실패가 리스너 스레드 밖으로 번지지 않는다.")
    @Test
    void onMessageWhenPayloadIsBroken() {
        // given
        emitterRepository.save("7_1000", new SseEmitter());
        Message broken = new DefaultMessage(
                TOPIC.getBytes(StandardCharsets.UTF_8),
                "not-a-json".getBytes(StandardCharsets.UTF_8));

        // when // then
        assertThatCode(() -> notificationSubscriber.onMessage(broken, null))
                .doesNotThrowAnyException();

        then(notificationSender).shouldHaveNoInteractions();
    }

    private Message message(NotificationMessage payload) {
        return new DefaultMessage(
                TOPIC.getBytes(StandardCharsets.UTF_8),
                objectMapper.writeValueAsString(payload).getBytes(StandardCharsets.UTF_8));
    }

    private NotificationMessage notificationMessage(int notificationId) {
        return NotificationMessage.builder()
                .notificationId(notificationId)
                .type(NotificationType.TREE_CREATED)
                .receiverId(RECEIVER_ID)
                .message(NotificationType.TREE_CREATED.getMessage())
                .createdAt(LocalDateTime.of(2026, 8, 4, 15, 21, 3))
                .build();
    }
}
