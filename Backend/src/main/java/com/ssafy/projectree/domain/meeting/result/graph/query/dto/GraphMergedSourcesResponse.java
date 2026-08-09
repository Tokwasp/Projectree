package com.ssafy.projectree.domain.meeting.result.graph.query.dto;

import java.time.Instant;
import java.util.List;

public record GraphMergedSourcesResponse(
        int projectId,
        long graphVersion,
        Instant graphSyncedAt,
        String targetNodeId,
        List<GraphNodeDetailItemResponse> items
) {
}
