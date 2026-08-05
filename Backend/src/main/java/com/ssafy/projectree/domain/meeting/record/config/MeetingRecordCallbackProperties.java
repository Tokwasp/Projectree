package com.ssafy.projectree.domain.meeting.record.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * apiKey가 비어 있으면 Callback 인증은 항상 실패한다.
 * 비어 있는 설정을 기동 시점에 거부하지 않는 이유는, 회의록 Callback을 사용하지 않는 환경에서도
 * 애플리케이션이 기동되어야 하기 때문이다.
 */
@ConfigurationProperties(prefix = "app.meeting-record.callback")
public record MeetingRecordCallbackProperties(String apiKey) {

    public MeetingRecordCallbackProperties {
        apiKey = apiKey == null ? "" : apiKey;
    }

    public boolean hasApiKey() {
        return !apiKey.isBlank();
    }
}
