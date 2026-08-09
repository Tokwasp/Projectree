package com.ssafy.projectree.domain.meeting.result.graph.command;

import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;

public record NodeContentUpdateRejectedPayload(
        GraphResultSourceType sourceType,
        NodeContentUpdateRejectionReason reasonCode,
        String failedNodeId
) {
}
