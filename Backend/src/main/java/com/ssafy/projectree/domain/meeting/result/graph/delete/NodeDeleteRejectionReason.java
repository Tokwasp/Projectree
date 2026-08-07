package com.ssafy.projectree.domain.meeting.result.graph.delete;

public enum NodeDeleteRejectionReason {
    GRAPH_VERSION_CONFLICT,
    NODE_NOT_FOUND,
    NODE_PROJECT_MISMATCH,
    NODE_DELETE_SET_INCOMPLETE
}
