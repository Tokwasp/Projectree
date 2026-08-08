package com.ssafy.projectree.domain.meeting.result.graph.operation;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum ProjectGraphOperationErrorCode implements ErrorCode {
    GRAPH_OPERATION_IN_PROGRESS(
            HttpStatus.CONFLICT,
            "그래프 변경 작업이 진행 중입니다. 작업이 완료된 후 다시 시도해주세요."
    ),
    PROJECT_GRAPH_SYNC_NOT_FOUND(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "프로젝트 그래프 동기화 상태를 찾을 수 없습니다."
    );

    private final HttpStatus status;
    private final String message;
}
