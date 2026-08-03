package com.ssafy.projectree.domain.project.exception;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum ProjectErrorCode implements ErrorCode {
    PROJECT_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 프로젝트입니다."),
    NOT_PROJECT_OWNER(HttpStatus.FORBIDDEN, "프로젝트 소유자만 가능한 작업입니다."),
    ALREADY_PROJECT_MEMBER(HttpStatus.CONFLICT, "이미 프로젝트 멤버입니다.");

    private final HttpStatus status;
    private final String message;
}
