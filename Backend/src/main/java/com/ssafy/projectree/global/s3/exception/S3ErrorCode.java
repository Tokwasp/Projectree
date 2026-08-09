package com.ssafy.projectree.global.s3.exception;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum S3ErrorCode implements ErrorCode {

    // 500
    PRESIGNED_URL_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "업로드 URL 발급에 실패했습니다.");

    private final HttpStatus status;
    private final String message;
}
