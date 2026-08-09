package com.ssafy.projectree.domain.project.entity;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@RequiredArgsConstructor
@Getter
public enum ProjectMemberErrorCode implements ErrorCode {
    IS_NOT_PROJECT_MEMBER(HttpStatus.BAD_REQUEST, "해당 프로젝트의 맴버가 아닙니다."),
    IS_NOT_PROJECT_OWNER(HttpStatus.FORBIDDEN, "해당 프로젝트의 OWNER가 아닙니다.");

    private final HttpStatus status;
    private final String message;
}
