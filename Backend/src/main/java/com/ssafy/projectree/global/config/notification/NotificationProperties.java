package com.ssafy.projectree.global.config.notification;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

/**
 * heartbeat-interval 은 @Scheduled 가 fixedRateString 으로 직접 읽으므로 여기 두지 않는다.
 */
@Getter
@ConfigurationProperties(prefix = "app.notification")
@RequiredArgsConstructor
public class NotificationProperties {

    private final Sse sse;

    @Getter
    @RequiredArgsConstructor
    public static class Sse {

        private final Duration timeout;
    }
}
