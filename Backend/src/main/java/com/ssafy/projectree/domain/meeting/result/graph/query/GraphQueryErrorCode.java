package com.ssafy.projectree.domain.meeting.result.graph.query;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum GraphQueryErrorCode implements ErrorCode {

    INVALID_GRAPH_STATE_QUERY(HttpStatus.BAD_REQUEST, "graphState는 UNATTACHED만 조회할 수 있습니다."),
    NODE_NOT_FOUND(HttpStatus.NOT_FOUND, "해당 프로젝트의 Graph Node를 찾을 수 없습니다."),
    INVALID_MERGED_SOURCE_TARGET(HttpStatus.BAD_REQUEST, "병합 Source 조회 대상은 ACTIVE Node여야 합니다."),
    GRAPH_PROJECTION_INCONSISTENT(HttpStatus.INTERNAL_SERVER_ERROR, "Graph Projection 데이터가 일관되지 않습니다.");

    private final HttpStatus status;
    private final String message;
}
