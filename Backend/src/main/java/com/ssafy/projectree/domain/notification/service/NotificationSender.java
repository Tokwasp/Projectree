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

    public void sendSubscriptionMessage(int memberId, SseEmitter emitter, String eventName, Object data) {
        try {
            emitter.send(
                    SseEmitter.event()
                            .name(eventName)
                            .data(data, MediaType.APPLICATION_JSON)
            );
        } catch (IOException | IllegalStateException e) {
            log.debug("SSE 구독 실패 memberId={}", memberId);
            completeAndRemove(memberId, emitter);
        }
    }

    public void send(int memberId, SseEmitter emitter, String eventId, String eventName, Object data) {
        try {
            emitter.send(
                    SseEmitter.event()
                    .id(eventId)
                    .name(eventName)
                    .data(data, MediaType.APPLICATION_JSON)
            );
        } catch (IOException | IllegalStateException e) {
            log.debug("SSE 전송 실패 memberId={}", memberId);
            completeAndRemove(memberId, emitter);
        }
    }

    public void sendHeartbeat(int memberId, SseEmitter emitter) {
        try {
            emitter.send(
                    SseEmitter.event()
                    .comment("keep-alive")
            );
        } catch (IOException | IllegalStateException e) {
            log.debug("SSE 하트비트 체크 실패 memberId={}", memberId);
            completeAndRemove(memberId, emitter);
        }
    }

    public void completeAndRemove(int memberId, SseEmitter emitter) {
        emitterRepository.delete(memberId, emitter);
        try {
            emitter.complete();
        } catch (Exception e) {
            log.debug("이미 끊긴 emitter 정리 중 예외 무시 memberId={}", memberId);
        }
    }
}
