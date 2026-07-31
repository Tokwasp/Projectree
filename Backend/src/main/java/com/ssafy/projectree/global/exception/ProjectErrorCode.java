package com.ssafy.projectree.global.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum ProjectErrorCode implements ErrorCode {

    // 400
    INVALID_CATEGORY(HttpStatus.BAD_REQUEST, "유효하지 않은 카테고리입니다."),

    //403
    PROJECT_DELETE_FORBIDDEN(HttpStatus.FORBIDDEN, "프로젝트 삭제 권한이 없습니다."),
    PROJECT_LEAVE_FORBIDDEN(HttpStatus.FORBIDDEN, "프로젝트 탈퇴 권한이 없습니다."),

    // 404
    MEMBER_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 회원입니다."),
    PROJECT_PARTICIPANT_NOT_FOUND(HttpStatus.NOT_FOUND, "프로젝트에 참여 중인 회원이 아닙니다."),
    PROJECT_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 프로젝트입니다.");

    private final HttpStatus status;
    private final String message;
}
