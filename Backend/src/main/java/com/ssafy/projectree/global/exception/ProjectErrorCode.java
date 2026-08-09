package com.ssafy.projectree.global.exception;

import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum ProjectErrorCode implements ErrorCode {

    //403
    PROJECT_DELETE_FORBIDDEN(HttpStatus.FORBIDDEN, "프로젝트 삭제 권한이 없습니다."),
    PROJECT_LEAVE_FORBIDDEN(HttpStatus.FORBIDDEN, "프로젝트 탈퇴 권한이 없습니다."),

    // 409
    PROJECT_DELETE_ACTIVE_MEETING(HttpStatus.CONFLICT, "진행 중인 회의가 있어 프로젝트를 삭제할 수 없습니다."),
    PROJECT_DELETE_ANALYSIS_IN_PROGRESS(HttpStatus.CONFLICT, "회의 분석이 진행 중이라 프로젝트를 삭제할 수 없습니다."),
    PROJECT_DELETE_GRAPH_OPERATION_IN_PROGRESS(HttpStatus.CONFLICT, "그래프 변경 작업이 진행 중이라 프로젝트를 삭제할 수 없습니다."),

    // 503
    PROJECT_DELETE_STATE_CHECK_FAILED(HttpStatus.SERVICE_UNAVAILABLE, "현재 프로젝트 상태를 확인할 수 없어 삭제할 수 없습니다."),

    // 404
    MEMBER_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 회원입니다."),
    PROJECT_PARTICIPANT_NOT_FOUND(HttpStatus.NOT_FOUND, "프로젝트에 참여 중인 회원이 아닙니다."),
    PROJECT_NOT_FOUND(HttpStatus.NOT_FOUND, "존재하지 않는 프로젝트입니다.");

    private final HttpStatus status;
    private final String message;
}
