package com.ssafy.projectree.domain.member.exception;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum AuthErrorCode implements ErrorCode {
    GOOGLE_TOKEN_FAILED(HttpStatus.BAD_REQUEST, "구글 인증에 실패했습니다."),
    GOOGLE_PROFILE_FAILED(HttpStatus.BAD_REQUEST, "구글 프로필 조회에 실패했습니다."),
    NAVER_TOKEN_FAILED(HttpStatus.BAD_REQUEST, "네이버 인증에 실패했습니다."),
    NAVER_PROFILE_FAILED(HttpStatus.BAD_REQUEST, "네이버 프로필 조회에 실패했습니다."),
    NAVER_EMAIL_REQUIRED(HttpStatus.BAD_REQUEST, "네이버 계정의 이메일 제공 동의가 필요합니다."),
    DELETED_MEMBER(HttpStatus.NOT_FOUND,"이미 탈퇴한 사용자입니다.");

    private final HttpStatus status;
    private final String message;
}
