package com.ssafy.projectree.domain.meeting.result.graph.command.dto;

import java.util.UUID;

public record BatchNodeContentUpdateResponse(
        UUID commandId,
        int requestedNodeCount,
        int changedNodeCount,
        String status
) {

    public static BatchNodeContentUpdateResponse pending(
            UUID commandId,
            int requestedNodeCount,
            int changedNodeCount
    ) {
        return new BatchNodeContentUpdateResponse(
                commandId, requestedNodeCount, changedNodeCount, "PENDING"
        );
    }

    public static BatchNodeContentUpdateResponse noChange(int requestedNodeCount) {
        return new BatchNodeContentUpdateResponse(
                null, requestedNodeCount, 0, "NO_CHANGE"
        );
    }

    public boolean hasPendingCommand() {
        return commandId != null;
    }
}
