package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;

@Slf4j
@Component
@RequiredArgsConstructor
public class NotificationSender {

    public static final String NOTIFICATION_EVENT = "notification";
    private final EmitterRepository emitterRepository;

    public void sendSubscriptionMessage(String emitterId, SseEmitter emitter, String eventName, Object data) {
        try {
            emitter.send(
                    SseEmitter.event()
                            .name(eventName)
                            .data(data, MediaType.APPLICATION_JSON)
            );
        } catch (IOException | IllegalStateException e) {
            log.debug("SSE 구독 실패 emitterId={}", emitterId);
            emitterRepository.deleteById(emitterId);
            emitter.complete();
        }
    }

    public void send(String emitterId, SseEmitter emitter, String eventId, String eventName, Object data) {
        try {
            emitter.send(
                    SseEmitter.event()
                    .id(eventId)
                    .name(eventName)
                    .data(data, MediaType.APPLICATION_JSON)
            );
        } catch (IOException | IllegalStateException e) {
            log.debug("SSE 전송 실패 emitterId={}", emitterId);
            emitterRepository.deleteById(emitterId);
            emitter.complete();
        }
    }

    public void sendHeartbeat(String emitterId, SseEmitter emitter) {
        try {
            emitter.send(
                    SseEmitter.event()
                    .comment("keep-alive")
            );
        } catch (IOException | IllegalStateException e) {
            log.debug("SSE 하트비트 체크 실패 emitterId={}", emitterId);
            emitterRepository.deleteById(emitterId);
            emitter.complete();
        }
    }
}
