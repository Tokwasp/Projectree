package com.ssafy.projectree.global.exception;

import lombok.Getter;

@Getter
public class DomainException extends RuntimeException {

    private final ErrorCode errorCode;
    private final Domain domain;

    public DomainException(ErrorCode errorCode, Domain domain) {
        super(errorCode.getMessage());
        this.errorCode = errorCode;
        this.domain = domain;
    }
}
