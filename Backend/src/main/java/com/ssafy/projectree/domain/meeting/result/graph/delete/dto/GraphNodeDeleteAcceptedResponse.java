package com.ssafy.projectree.domain.meeting.result.graph.delete.dto;

import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus;

import java.util.List;
import java.util.UUID;

public record GraphNodeDeleteAcceptedResponse(
        UUID commandId,
        int projectId,
        List<String> nodeIds,
        long expectedGraphVersion,
        NodeDeleteCommandStatus status
) {

    public static GraphNodeDeleteAcceptedResponse pending(
            UUID commandId,
            int projectId,
            List<String> nodeIds,
            long expectedGraphVersion
    ) {
        return new GraphNodeDeleteAcceptedResponse(
                commandId,
                projectId,
                List.copyOf(nodeIds),
                expectedGraphVersion,
                NodeDeleteCommandStatus.PENDING
        );
    }
}
