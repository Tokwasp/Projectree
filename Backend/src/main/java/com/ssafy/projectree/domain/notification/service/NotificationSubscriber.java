package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.dto.NotificationMessage;
import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;

@Slf4j
@Component
@RequiredArgsConstructor
public class NotificationSubscriber implements MessageListener {

    private final ObjectMapper objectMapper;
    private final EmitterRepository emitterRepository;
    private final NotificationSender notificationSender;

    @Override
    public void onMessage(Message message, byte[] pattern) {
        try {
            NotificationMessage payload = objectMapper.readValue(
                    new String(message.getBody(), StandardCharsets.UTF_8),
                    NotificationMessage.class);

            emitterRepository.findAllByMemberId(payload.getReceiverId())
                    .forEach(emitter -> notificationSender.send(
                            payload.getReceiverId(),
                            emitter,
                            String.valueOf(payload.getNotificationId()),
                            NotificationSender.NOTIFICATION_EVENT,
                            payload));

        } catch (Exception e) {
            log.error("알림 메시지 처리에 실패했다", e);
        }
    }
}
