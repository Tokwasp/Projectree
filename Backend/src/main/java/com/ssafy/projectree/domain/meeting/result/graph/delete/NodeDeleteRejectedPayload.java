package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;

public record NodeDeleteRejectedPayload(
        GraphResultSourceType sourceType,
        NodeDeleteRejectionReason reasonCode
) {
}
