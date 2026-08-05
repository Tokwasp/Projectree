package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

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
