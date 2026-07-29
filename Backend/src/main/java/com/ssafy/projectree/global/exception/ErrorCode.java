package com.ssafy.projectree.global.exception;

import org.springframework.http.HttpStatus;

public interface ErrorCode {
    HttpStatus getStatus();
    String getMessage();

    default String getDomain() {
        return getClass().getSimpleName().replace("ErrorCode", "").toUpperCase();
    }
}
