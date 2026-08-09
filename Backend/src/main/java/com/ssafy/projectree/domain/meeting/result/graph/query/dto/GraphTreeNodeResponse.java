package com.ssafy.projectree.domain.meeting.result.graph.query.dto;

import com.ssafy.projectree.domain.meeting.result.graph.query.GraphTreeNodeKind;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;

import java.time.Instant;
import java.util.List;

public record GraphTreeNodeResponse(
        String id,
        GraphTreeNodeKind kind,
        String title,
        GraphNodeCategory category,
        GraphNodeType nodeType,
        Integer sourceMeetingId,
        Long nodeVersion,
        Instant updatedAt,
        List<GraphTreeNodeResponse> children
) {
}
