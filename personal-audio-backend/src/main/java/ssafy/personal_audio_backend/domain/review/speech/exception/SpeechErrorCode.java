package ssafy.personal_audio_backend.domain.review.speech.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import ssafy.personal_audio_backend.global.exception.ErrorCode;

@Getter
@RequiredArgsConstructor
public enum SpeechErrorCode implements ErrorCode {

    SPEECH_SEGMENT_NEGATIVE_START(HttpStatus.INTERNAL_SERVER_ERROR, "발화 구간의 시작은 음수일 수 없습니다."),
    SPEECH_SEGMENT_INVALID_RANGE(HttpStatus.INTERNAL_SERVER_ERROR, "발화 구간의 끝은 시작보다 뒤여야 합니다.");

    private final HttpStatus status;
    private final String message;
}
