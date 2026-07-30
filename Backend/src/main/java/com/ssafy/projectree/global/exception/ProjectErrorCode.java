package com.ssafy.projectree.global.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum ProjectErrorCode implements ErrorCode {

    // 400
    INVALID_REQUEST(HttpStatus.BAD_REQUEST, "유효하지 않은 카테고리입니다."),

    // 404
    MEMBER_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 회원입니다.");

    private final HttpStatus status;
    private final String message;
}
