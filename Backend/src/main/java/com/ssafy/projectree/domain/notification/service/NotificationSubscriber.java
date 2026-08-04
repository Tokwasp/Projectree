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

    /**
     * 이 메서드는 절대 예외를 밖으로 던지지 않는다.
     * 한 건의 실패가 다음 메시지 수신을 막지 않게 한다.
     * <p>
     * Emitter 가 하나도 없으면 아무 일도 일어나지 않는다. 그 사용자가 다른 인스턴스에 붙어 있거나
     * 접속 중이 아니라는 뜻이므로 오류가 아니다.
     */
    @Override
    public void onMessage(Message message, byte[] pattern) {
        try {
            NotificationMessage payload = objectMapper.readValue(
                    new String(message.getBody(), StandardCharsets.UTF_8),
                    NotificationMessage.class);

            emitterRepository.findAllByMemberId(payload.getReceiverId())
                    .forEach((emitterId, emitter) -> notificationSender.send(
                            emitterId,
                            emitter,
                            String.valueOf(payload.getNotificationId()),
                            NotificationSender.NOTIFICATION_EVENT,
                            payload));

        } catch (Exception e) {
            log.error("알림 메시지 처리에 실패했다", e);
        }
    }
}
