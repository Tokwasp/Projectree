package com.ssafy.projectree.domain.meetingreview.exception;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@RequiredArgsConstructor
@Getter
public enum MeetingReviewErrorCode implements ErrorCode {

    IS_NOT_PROJECT_MEMBER(HttpStatus.BAD_REQUEST, "해당 프로젝트 회원이 아닙니다.");

    private final HttpStatus status;
    private final String message;
}
