package ssafy.personal_audio_backend.domain.review.feedback.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import ssafy.personal_audio_backend.global.exception.ErrorCode;

@Getter
@RequiredArgsConstructor
public enum FeedbackErrorCode implements ErrorCode {

    FEEDBACK_EMPTY(HttpStatus.BAD_GATEWAY, "AI 피드백 내용이 비어 있습니다."),
    TRANSCRIPT_EMPTY(HttpStatus.BAD_GATEWAY, "음성에서 대본을 얻지 못했습니다.");

    private final HttpStatus status;
    private final String message;
}
