package com.ssafy.projectree.global.response;

import lombok.Getter;
import org.springframework.http.HttpStatus;

@Getter
public class ApiResponse<T> {

    private final int status;
    private final String message;
    private final T data;

    private ApiResponse(int status, String message, T data) {
        this.status = status;
        this.message = message;
        this.data = data;
    }

    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(HttpStatus.OK.value(), "성공", data);
    }

    public static ApiResponse<Void> success() {
        return new ApiResponse<>(HttpStatus.OK.value(), "성공", null);
    }
}
