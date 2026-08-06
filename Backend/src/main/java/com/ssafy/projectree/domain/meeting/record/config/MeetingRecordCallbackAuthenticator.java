package com.ssafy.projectree.domain.meeting.record.config;

import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

/**
 * 내부 Callback 전용 공유 비밀 검증.
 * 설정값과 전달값 중 어느 것도 로그나 예외 메시지에 남기지 않는다.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class MeetingRecordCallbackAuthenticator {

    private final MeetingRecordCallbackProperties properties;

    public void authenticate(String providedApiKey) {
        if (!properties.hasApiKey()) {
            log.warn("회의록 Callback API Key가 설정되지 않아 인증을 거부한다.");
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_CALLBACK_UNAUTHORIZED);
        }
        if (providedApiKey == null || providedApiKey.isBlank()) {
            log.warn("회의록 Callback 요청에 인증 헤더가 없다.");
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_CALLBACK_UNAUTHORIZED);
        }
        if (!matches(providedApiKey)) {
            log.warn("회의록 Callback 인증 헤더가 설정값과 일치하지 않는다.");
            throw new CustomException(MeetingRecordErrorCode.MEETING_RECORD_CALLBACK_UNAUTHORIZED);
        }
    }

    /**
     * 길이 정보까지 감추지는 못하지만, 최소한 앞자리 일치 개수가 응답 시간으로 새지 않도록
     * 단축 평가 없이 바이트 배열을 비교한다.
     */
    private boolean matches(String providedApiKey) {
        return MessageDigest.isEqual(
                properties.apiKey().getBytes(StandardCharsets.UTF_8),
                providedApiKey.getBytes(StandardCharsets.UTF_8)
        );
    }
}
