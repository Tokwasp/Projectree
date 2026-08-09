package com.ssafy.projectree.global.response;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;

@Getter
public class ApiErrorResponse {

    private final int status;
    private final ErrorCode errorCode;
    private final String errorMessage;

    private ApiErrorResponse(ErrorCode errorCode) {
        this.status = errorCode.getStatus().value();
        this.errorCode = errorCode;
        this.errorMessage = errorCode.getMessage();
    }

    public ApiErrorResponse(ErrorCode errorCode, String errorMessage) {
        this.status = errorCode.getStatus().value();
        this.errorCode = errorCode;
        this.errorMessage = errorMessage;
    }

    public static ApiErrorResponse of(ErrorCode errorCode) {
        return new ApiErrorResponse(errorCode);
    }

    public static ApiErrorResponse of(ErrorCode errorCode, String errorMessage) {
        return new ApiErrorResponse(errorCode, errorMessage);
    }
}
