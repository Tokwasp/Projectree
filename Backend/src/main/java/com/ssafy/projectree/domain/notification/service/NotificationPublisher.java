package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.dto.NotificationMessage;
import com.ssafy.projectree.global.config.notification.NotificationConfig;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;
import tools.jackson.databind.ObjectMapper;

/**
 * 기본 타이핑이 붙은 직렬화로 객체를 그대로 발행하지 않는다.
 * 페이로드에 @class(FQCN)가 박히면 두 서버의 클래스 경로가 완전히 같아야 하고,
 * 패키지를 옮기면 배포 중 메시지가 깨진다. 평범한 JSON 문자열이 서버 간 계약으로 더 안전하다.
 */
@Component
@RequiredArgsConstructor
public class NotificationPublisher {

    private final StringRedisTemplate stringRedisTemplate;
    private final ObjectMapper objectMapper;

    public void publish(NotificationMessage message) {
        stringRedisTemplate.convertAndSend(
                NotificationConfig.NOTIFICATION_TOPIC,
                objectMapper.writeValueAsString(message));
    }
}
