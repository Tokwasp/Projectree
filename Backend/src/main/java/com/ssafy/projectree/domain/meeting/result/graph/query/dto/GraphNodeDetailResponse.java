package com.ssafy.projectree.domain.meeting.result.graph.query.dto;

import java.time.Instant;

public record GraphNodeDetailResponse(
        int projectId,
        long graphVersion,
        Instant graphSyncedAt,
        GraphNodeDetailItemResponse node
) {
}
