package com.ssafy.projectree.global.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum ErrorCode {

    INVALID_REQUEST(HttpStatus.BAD_REQUEST, "요청 값이 올바르지 않습니다."),
    NAVER_TOKEN_FAILED(HttpStatus.BAD_REQUEST, "네이버 인증에 실패했습니다."),
    NAVER_PROFILE_FAILED(HttpStatus.BAD_REQUEST, "네이버 프로필 조회에 실패했습니다."),
    NAVER_EMAIL_REQUIRED(HttpStatus.BAD_REQUEST, "네이버 계정의 이메일 제공 동의가 필요합니다.");

    private final HttpStatus status;
    private final String message;
}
