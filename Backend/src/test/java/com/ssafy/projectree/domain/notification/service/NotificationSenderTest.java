package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyEmitter;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.util.stream.Collectors;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;

@ExtendWith(MockitoExtension.class)
class NotificationSenderTest {

    private static final String EMITTER_ID = "7_1000";

    @InjectMocks
    private NotificationSender notificationSender;

    @Mock
    private EmitterRepository emitterRepository;

    @Mock
    private SseEmitter emitter;

    @DisplayName("알림은 알림 id를 이벤트 id로 삼아 notification 이벤트로 나간다.")
    @Test
    void send() throws Exception {
        // when
        notificationSender.send(EMITTER_ID, emitter, "41", NotificationSender.NOTIFICATION_EVENT, "본문");

        // then
        assertThat(capturedEvent()).contains("id:41", "event:notification");
    }

    @DisplayName("구독 메시지에는 이벤트 id 를 붙이지 않아 브라우저의 Last-Event-ID 를 덮어쓰지 않는다.")
    @Test
    void sendSubscriptionMessage() throws Exception {
        // when
        notificationSender.sendSubscriptionMessage(EMITTER_ID, emitter, "connect", "연결되었습니다.");

        // then
        assertThat(capturedEvent())
                .contains("event:connect")
                .doesNotContain("id:");
    }

    @DisplayName("하트비트는 이벤트가 아니라 주석으로 나가 프론트가 처리할 것이 없다.")
    @Test
    void sendHeartbeat() throws Exception {
        // when
        notificationSender.sendHeartbeat(EMITTER_ID, emitter);

        // then
        assertThat(capturedEvent())
                .contains(":keep-alive")
                .doesNotContain("event:");
    }

    @DisplayName("이미 닫힌 브라우저로 전송하면 예외를 밖으로 던지지 않고 연결을 정리한다.")
    @Test
    void sendWhenClientAlreadyClosed() throws Exception {
        // given
        doThrow(new IOException("Broken pipe")).when(emitter).send(any(SseEmitter.SseEventBuilder.class));

        // when // then
        assertThatCode(() -> notificationSender.send(
                EMITTER_ID, emitter, "41", NotificationSender.NOTIFICATION_EVENT, "본문"))
                .doesNotThrowAnyException();

        then(emitterRepository).should().deleteById(EMITTER_ID);
        then(emitter).should().complete();
    }

    @DisplayName("이미 종료된 emitter로 전송하면 예외를 밖으로 던지지 않고 연결을 정리한다.")
    @Test
    void sendWhenEmitterAlreadyCompleted() throws Exception {
        // given
        doThrow(new IllegalStateException("ResponseBodyEmitter has already completed"))
                .when(emitter).send(any(SseEmitter.SseEventBuilder.class));

        // when // then
        assertThatCode(() -> notificationSender.send(
                EMITTER_ID, emitter, "41", NotificationSender.NOTIFICATION_EVENT, "본문"))
                .doesNotThrowAnyException();

        then(emitterRepository).should().deleteById(EMITTER_ID);
        then(emitter).should().complete();
    }

    @DisplayName("하트비트 전송이 실패하면 죽은 연결로 보고 정리한다.")
    @Test
    void sendHeartbeatWhenClientAlreadyClosed() throws Exception {
        // given
        doThrow(new IOException("Broken pipe")).when(emitter).send(any(SseEmitter.SseEventBuilder.class));

        // when // then
        assertThatCode(() -> notificationSender.sendHeartbeat(EMITTER_ID, emitter))
                .doesNotThrowAnyException();

        then(emitterRepository).should().deleteById(EMITTER_ID);
    }

    @DisplayName("전송에 성공하면 연결을 정리하지 않는다.")
    @Test
    void sendKeepsEmitterWhenSucceeded() {
        // when
        notificationSender.send(EMITTER_ID, emitter, "41", NotificationSender.NOTIFICATION_EVENT, "본문");

        // then
        then(emitterRepository).should(never()).deleteById(EMITTER_ID);
    }

    private String capturedEvent() throws IOException {
        ArgumentCaptor<SseEmitter.SseEventBuilder> captor =
                ArgumentCaptor.forClass(SseEmitter.SseEventBuilder.class);
        then(emitter).should().send(captor.capture());

        return captor.getValue().build().stream()
                .map(ResponseBodyEmitter.DataWithMediaType::getData)
                .map(String::valueOf)
                .collect(Collectors.joining());
    }
}
