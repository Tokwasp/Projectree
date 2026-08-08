package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.global.exception.ErrorCode;
import lombok.Getter;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;

@Getter
@RequiredArgsConstructor
public enum GraphNodeDeleteErrorCode implements ErrorCode {
    GRAPH_VERSION_CONFLICT(
            HttpStatus.CONFLICT,
            "Graph version does not match the current project graph"
    ),
    NODE_DELETE_DUPLICATE_NODE_ID(
            HttpStatus.BAD_REQUEST,
            "Node delete request contains duplicate node IDs"
    ),
    NODE_DELETE_SET_INCOMPLETE(
            HttpStatus.CONFLICT,
            "Node delete request must include every active descendant"
    ),
    NODE_DELETE_SERIALIZATION_FAILED(
            HttpStatus.INTERNAL_SERVER_ERROR,
            "Failed to serialize node delete command"
    ),
    NODE_DELETE_COMMAND_NOT_FOUND(
            HttpStatus.NOT_FOUND,
            "Node delete command was not found"
    );

    private final HttpStatus status;
    private final String message;
}
