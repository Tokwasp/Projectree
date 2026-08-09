package com.ssafy.projectree.domain.meeting.record.config;

import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingRecordCallbackAuthenticatorTest {

    private static final String CONFIGURED_KEY = "test-callback-key";

    private final MeetingRecordCallbackAuthenticator authenticator =
            new MeetingRecordCallbackAuthenticator(
                    new MeetingRecordCallbackProperties(CONFIGURED_KEY)
            );

    @DisplayName("설정값과 동일한 API Key는 인증을 통과한다.")
    @Test
    void authenticatesMatchingApiKey() {
        assertThatCode(() -> authenticator.authenticate(CONFIGURED_KEY))
                .doesNotThrowAnyException();
    }

    @DisplayName("헤더가 없거나 비어 있으면 인증에 실패한다.")
    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "\t"})
    void rejectsMissingHeader(String providedApiKey) {
        assertUnauthorized(() -> authenticator.authenticate(providedApiKey));
    }

    @DisplayName("설정값과 다른 API Key는 인증에 실패한다.")
    @ParameterizedTest
    @ValueSource(strings = {
            "wrong-callback-key",
            "test-callback-ke",
            "test-callback-key ",
            "TEST-CALLBACK-KEY",
            "test-callback-keyy"
    })
    void rejectsWrongApiKey(String providedApiKey) {
        assertUnauthorized(() -> authenticator.authenticate(providedApiKey));
    }

    @DisplayName("설정된 API Key가 없으면 올바른 값을 알 수 없으므로 항상 인증에 실패한다.")
    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" "})
    void rejectsEveryRequestWhenApiKeyIsNotConfigured(String configuredKey) {
        MeetingRecordCallbackAuthenticator unconfigured =
                new MeetingRecordCallbackAuthenticator(
                        new MeetingRecordCallbackProperties(configuredKey)
                );

        assertUnauthorized(() -> unconfigured.authenticate(CONFIGURED_KEY));
        assertUnauthorized(() -> unconfigured.authenticate(configuredKey));
    }

    @DisplayName("인증 실패 예외 메시지에 설정값이나 전달값이 노출되지 않는다.")
    @Test
    void doesNotLeakApiKeyInExceptionMessage() {
        String provided = "leaked-provided-key";

        assertThatThrownBy(() -> authenticator.authenticate(provided))
                .isInstanceOf(CustomException.class)
                .hasMessageNotContaining(CONFIGURED_KEY)
                .hasMessageNotContaining(provided)
                .hasMessage(MeetingRecordErrorCode.MEETING_RECORD_CALLBACK_UNAUTHORIZED.getMessage());
    }

    @DisplayName("빈 설정값은 빈 문자열로 정규화되고 hasApiKey는 false다.")
    @Test
    void normalizesNullApiKey() {
        assertThat(new MeetingRecordCallbackProperties(null).apiKey()).isEmpty();
        assertThat(new MeetingRecordCallbackProperties(null).hasApiKey()).isFalse();
        assertThat(new MeetingRecordCallbackProperties(" ").hasApiKey()).isFalse();
        assertThat(new MeetingRecordCallbackProperties(CONFIGURED_KEY).hasApiKey()).isTrue();
    }

    private void assertUnauthorized(Runnable action) {
        assertThatThrownBy(action::run)
                .isInstanceOf(CustomException.class)
                .extracting(error -> ((CustomException) error).getErrorCode())
                .isEqualTo(MeetingRecordErrorCode.MEETING_RECORD_CALLBACK_UNAUTHORIZED);
    }
}
