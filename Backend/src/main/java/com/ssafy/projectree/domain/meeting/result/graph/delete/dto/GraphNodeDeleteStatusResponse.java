package com.ssafy.projectree.domain.meeting.result.graph.delete.dto;

import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus;

import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

public record GraphNodeDeleteStatusResponse(
        UUID commandId,
        int projectId,
        List<String> nodeIds,
        long expectedGraphVersion,
        Long resultGraphVersion,
        NodeDeleteCommandStatus status,
        String reason,
        LocalDateTime requestedAt,
        LocalDateTime completedAt
) {
}
