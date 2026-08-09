package com.ssafy.projectree.domain.meeting.result.graph.query.dto;

import java.time.Instant;
import java.util.List;

public record GraphNodePageResponse(
        int projectId,
        long graphVersion,
        Instant graphSyncedAt,
        List<GraphNodeSummaryResponse> items,
        int page,
        int size,
        long totalElements,
        int totalPages
) {
}
