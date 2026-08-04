package com.ssafy.projectree.domain.meeting.exception;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum MeetingErrorCode implements ErrorCode {

    INVALID_ROOM_NAME(HttpStatus.BAD_REQUEST, "올바른 UUID 형식의 roomName이 아닙니다."),
    MEETING_NOT_FOUND(HttpStatus.NOT_FOUND, "해당 프로젝트의 회의를 찾을 수 없습니다."),
    MEETING_ACCESS_DENIED(HttpStatus.FORBIDDEN, "해당 회의의 프로젝트 멤버가 아닙니다."),
    MEETING_ANALYSIS_ALREADY_REQUESTED(HttpStatus.CONFLICT, "회의 분석 요청이 이미 확정되었습니다."),
    OUTBOX_SERIALIZATION_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "분석 요청 메시지 생성에 실패했습니다.");

    private final HttpStatus status;
    private final String message;
}
