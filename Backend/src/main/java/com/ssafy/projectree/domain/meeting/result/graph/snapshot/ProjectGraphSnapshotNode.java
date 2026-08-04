package com.ssafy.projectree.domain.meeting.result.graph.snapshot;

import java.time.Instant;

public record ProjectGraphSnapshotNode(
        String nodeId,
        Integer sourceMeetingId,
        String parentNodeId,
        String mergedIntoNodeId,
        GraphNodeType nodeType,
        GraphNodeCategory category,
        GraphNodeState graphState,
        String title,
        String content,
        GraphLinkSource linkSource,
        long nodeVersion,
        Instant createdAt,
        Instant updatedAt
) {
}
