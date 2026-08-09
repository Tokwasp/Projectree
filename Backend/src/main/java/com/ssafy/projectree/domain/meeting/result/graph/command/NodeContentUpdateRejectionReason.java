package com.ssafy.projectree.domain.meeting.result.graph.command;

public enum NodeContentUpdateRejectionReason {

    NODE_NOT_FOUND(true),
    NODE_NOT_EDITABLE(true),
    MERGED_SOURCE_NOT_EDITABLE(true),
    NODE_VERSION_CONFLICT(true),
    INVALID_CURRENT_REVISION(true),

    NO_CHANGE(false),
    GRAPH_SNAPSHOT_TOO_LARGE(false);

    private final boolean failedNodeIdRequired;

    NodeContentUpdateRejectionReason(boolean failedNodeIdRequired) {
        this.failedNodeIdRequired = failedNodeIdRequired;
    }

    public boolean requiresFailedNodeId() {
        return failedNodeIdRequired;
    }
}
