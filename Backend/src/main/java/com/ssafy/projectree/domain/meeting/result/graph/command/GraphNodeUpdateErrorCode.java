package com.ssafy.projectree.domain.meeting.result.graph.command;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum GraphNodeUpdateErrorCode implements ErrorCode {
    NODE_UPDATE_EMPTY(HttpStatus.BAD_REQUEST, "수정할 제목 또는 내용을 입력해 주세요."),
    NODE_VERSION_CONFLICT(HttpStatus.CONFLICT, "노드 버전이 일치하지 않습니다."),
    NODE_TITLE_INVALID(HttpStatus.BAD_REQUEST, "노드 제목 형식이 올바르지 않습니다."),
    NODE_CONTENT_INVALID(HttpStatus.BAD_REQUEST, "노드 내용 형식이 올바르지 않습니다."),
    NODE_UPDATE_SERIALIZATION_FAILED(HttpStatus.INTERNAL_SERVER_ERROR, "노드 수정 명령을 생성하지 못했습니다.");

    private final HttpStatus status;
    private final String message;
}
