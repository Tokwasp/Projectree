package com.ssafy.projectree.global.exception;

import lombok.Getter;

/**
 * 비즈니스 규칙 위반을 나타내는 예외
 * ErrorCode를 들고 있어 GlobalExceptionHandler가 상태 코드와 메시지를 그대로 사용
 */
@Getter
public class BusinessException extends RuntimeException {

    private final ErrorCode errorCode;

    public BusinessException(ErrorCode errorCode) {
        super(errorCode.getMessage());
        this.errorCode = errorCode;
    }
}
