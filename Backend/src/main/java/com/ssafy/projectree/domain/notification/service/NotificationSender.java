package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;

/**
 * 전송과 실패 처리를 한 곳에 모은다.
 * 구독 시 더미 이벤트, 재전송, Redis 수신 시 전송, 하트비트 — 네 곳이 같은 실패 처리를 필요로 한다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class NotificationSender {

    public static final String CONNECT_EVENT = "connect";
    public static final String NOTIFICATION_EVENT = "notification";

    private static final String HEARTBEAT_COMMENT = "keep-alive";

    private final EmitterRepository emitterRepository;

    /**
     * data 의 두 번째 인자를 빼면 text/plain 으로 취급해 객체가 toString() 결과로 나간다.
     * 프론트가 JSON.parse 에서 깨진다.
     */
    public void send(String emitterId, SseEmitter emitter, String eventId, String eventName, Object data) {
        send(emitterId, emitter, SseEmitter.event()
                .id(eventId)
                .name(eventName)
                .data(data, MediaType.APPLICATION_JSON));
    }

    /**
     * 주석 라인은 표준상 EventSource 가 완전히 무시한다.
     * 목적은 바이트를 흘려 ALB 의 idle 타이머를 초기화하는 것뿐이다.
     */
    public void sendHeartbeat(String emitterId, SseEmitter emitter) {
        send(emitterId, emitter, SseEmitter.event().comment(HEARTBEAT_COMMENT));
    }

    private void send(String emitterId, SseEmitter emitter, SseEmitter.SseEventBuilder event) {
        try {
            emitter.send(event);
        } catch (IOException | IllegalStateException e) {
            // 브라우저가 이미 닫혔거나 emitter 가 종료된 경우다.
            // 한 사람의 죽은 연결 때문에 콜백 처리 전체가 실패하면 안 되므로 예외로 키우지 않는다.
            log.debug("SSE 전송 실패로 emitter 를 정리한다: emitterId={}", emitterId);
            emitterRepository.deleteById(emitterId);
            emitter.complete();
        }
    }
}
