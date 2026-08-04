package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

/**
 * ALB 의 idle timeout 은 기본 60초라 아무 바이트도 흐르지 않으면 연결이 끊긴다.
 * 각 인스턴스가 자기 메모리의 Emitter 만 순회하므로 분산 락이 필요 없다.
 * 모든 인스턴스에서 동시에 도는 것이 정상이다.
 */
@Component
@RequiredArgsConstructor
public class NotificationHeartbeatScheduler {

    private final EmitterRepository emitterRepository;
    private final NotificationSender notificationSender;

    @Scheduled(fixedRateString = "${app.notification.sse.heartbeat-interval}")
    public void sendHeartbeat() {
        emitterRepository.findAll().forEach((memberId, emitters) ->
                emitters.forEach(emitter -> notificationSender.sendHeartbeat(memberId, emitter)));
    }
}
