package com.ssafy.projectree.global.config.notification;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

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
