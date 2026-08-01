package ssafy.personal_audio_backend.service.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import ssafy.personal_audio_backend.global.exception.ErrorCode;

@Getter
@RequiredArgsConstructor
public enum AudioErrorCode implements ErrorCode {

    AUDIO_NOT_FOUND(HttpStatus.NOT_FOUND, "음성 파일이 존재하지 않습니다."),
    AUDIO_DOWNLOAD_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "음성 파일을 내려받지 못했습니다.");

    private final HttpStatus status;
    private final String message;
}
