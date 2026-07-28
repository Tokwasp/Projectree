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

    /**
     * 비즈니스 예외는 ErrorCode에 정의된 상태 코드와 메시지를 그대로 내려주도록
     */
    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ApiErrorResponse> handleBusinessException(BusinessException e) {
        ErrorCode errorCode = e.getErrorCode();
        log.warn("business exception: {}", errorCode);

        return ResponseEntity
                .status(errorCode.getStatus())
                .body(ApiErrorResponse.of(errorCode));
    }

    /**
     * @Valid 검증 실패
     */
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

    /**
     * 요청 본문이 JSON으로 파싱되지 않는 경우.
     */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiErrorResponse> handleHttpMessageNotReadable(
            HttpMessageNotReadableException e
    ) {
        log.warn("unreadable request body: {}", e.getMessage());

        return errorResponse(ErrorCode.INVALID_REQUEST);
    }

    /**
     * 나머지 예외를 처리
     * Spring MVC 표준 예외(405, 415, 404 등)는 ErrorResponse를 구현하고 있으므로
     * 그 상태 코드를 살려서 내려준다. 이 분기가 없으면 전부 500으로 나간다.
     * ErrorResponse는 인터페이스라 @ExceptionHandler에 직접 지정할 수 없어 여기서 instanceof로 갈라낸다.
     */
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

    /**
     * 매핑하지 않은 4xx는 INVALID_REQUEST(400)로 모은다.
     * 실제로 발생 가능한 406 등은 400으로 내려가므로, 필요해지면 ErrorCode를 추가한다.
     */
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
