package com.ssafy.projectree.global.exception;

import com.ssafy.projectree.global.response.ApiErrorResponse;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.ErrorResponse;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiErrorResponse> handleBusinessException(BusinessException e) {
        ErrorCode errorCode = e.getErrorCode();
        log.warn("business exception: {}", errorCode);

        return ResponseEntity
                .status(errorCode.getStatus())
                .body(ApiErrorResponse.of(errorCode));
    }

    @ExceptionHandler(DomainException.class)
    public ResponseEntity<ApiErrorResponse> handleDomainException(DomainException e) {
        ErrorCode errorCode = e.getErrorCode();
        Domain domain = e.getDomain();
        log.warn("domain exception: {}", errorCode);

        return ResponseEntity
                .status(errorCode.getStatus())
                .body(ApiErrorResponse.of(errorCode, domain.getDescription()));
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiErrorResponse> handleMethodArgumentNotValid(
            MethodArgumentNotValidException e
    ) {
        String fieldErrors = e.getBindingResult().getFieldErrors().stream()
                .map(this::formatFieldError)
                .reduce((a, b) -> a + ", " + b)
                .orElse("");
        log.warn("validation failed: {}", fieldErrors);

        return errorResponse(ErrorCode.INVALID_REQUEST);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiErrorResponse> handleHttpMessageNotReadable(
            HttpMessageNotReadableException e
    ) {
        log.warn("unreadable request body: {}", e.getMessage());

        return errorResponse(ErrorCode.INVALID_REQUEST);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ApiErrorResponse> handleException(Exception e) {
        if (e instanceof ErrorResponse springMvcError) {
            ErrorCode errorCode = toErrorCode(springMvcError.getStatusCode());
            log.warn("mvc exception: {} -> {}", springMvcError.getStatusCode(), errorCode);

            return errorResponse(errorCode);
        }

        log.error("unhandled exception", e);

        return errorResponse(ErrorCode.INTERNAL_SERVER_ERROR);
    }

    private ErrorCode toErrorCode(HttpStatusCode statusCode) {
        if (statusCode.equals(HttpStatus.NOT_FOUND)) {
            return ErrorCode.ENDPOINT_NOT_FOUND;
        }
        if (statusCode.equals(HttpStatus.METHOD_NOT_ALLOWED)) {
            return ErrorCode.METHOD_NOT_ALLOWED;
        }
        if (statusCode.equals(HttpStatus.UNSUPPORTED_MEDIA_TYPE)) {
            return ErrorCode.UNSUPPORTED_MEDIA_TYPE;
        }
        if (statusCode.is4xxClientError()) {
            return ErrorCode.INVALID_REQUEST;
        }
        return ErrorCode.INTERNAL_SERVER_ERROR;
    }

    private ResponseEntity<ApiErrorResponse> errorResponse(ErrorCode errorCode) {
        return ResponseEntity
                .status(errorCode.getStatus())
                .body(ApiErrorResponse.of(errorCode));
    }

    private String formatFieldError(FieldError fieldError) {
        return fieldError.getField() + ": " + fieldError.getDefaultMessage();
    }
}
