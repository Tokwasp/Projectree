package com.ssafy.projectree.domain.meeting.result.graph.query.dto;

import java.time.Instant;

public record GraphTreeResponse(
        int projectId,
        long graphVersion,
        Instant graphSyncedAt,
        GraphTreeNodeResponse root
) {
}
