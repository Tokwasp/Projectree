package com.ssafy.projectree.domain.meeting.result.graph.command.dto;

import java.util.UUID;

public record NodeContentUpdateAcceptedResponse(
        UUID commandId,
        String nodeId,
        long expectedNodeVersion,
        String status
) {

    public static NodeContentUpdateAcceptedResponse pending(
            UUID commandId,
            String nodeId,
            long expectedNodeVersion
    ) {
        return new NodeContentUpdateAcceptedResponse(
                commandId,
                nodeId,
                expectedNodeVersion,
                "PENDING"
        );
    }
}
