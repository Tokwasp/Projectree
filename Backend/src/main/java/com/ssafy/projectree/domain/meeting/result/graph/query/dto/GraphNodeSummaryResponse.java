package com.ssafy.projectree.domain.meeting.result.graph.query.dto;

import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphLinkSource;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;

import java.time.Instant;

public record GraphNodeSummaryResponse(
        String nodeId,
        Integer sourceMeetingId,
        String parentNodeId,
        String mergedIntoNodeId,
        GraphNodeType nodeType,
        GraphNodeCategory category,
        GraphNodeState graphState,
        String title,
        GraphLinkSource linkSource,
        long nodeVersion,
        Instant createdAt,
        Instant updatedAt
) {
}
