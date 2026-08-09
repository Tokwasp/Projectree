package ssafy.personal_audio_backend.global.client.gms.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import ssafy.personal_audio_backend.global.exception.ErrorCode;

@Getter
@RequiredArgsConstructor
public enum GmsErrorCode implements ErrorCode {

    GMS_REQUEST_FAILED(HttpStatus.BAD_GATEWAY, "AI 피드백 요청에 실패했습니다."),
    GMS_TIMEOUT(HttpStatus.GATEWAY_TIMEOUT, "AI 피드백 요청이 제한 시간을 넘었습니다."),
    GMS_RESPONSE_INVALID(HttpStatus.BAD_GATEWAY, "AI 피드백 응답을 해석하지 못했습니다."),
    GMS_AUDIO_TOO_LARGE(HttpStatus.PAYLOAD_TOO_LARGE, "음성 파일이 너무 커서 분석할 수 없습니다.");

    private final HttpStatus status;
    private final String message;
}
