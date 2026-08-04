package com.ssafy.projectree.domain.meeting.result.graph.event;

public record ProjectGraphChangedPayload(
        GraphResultSourceType sourceType,
        long graphVersion,
        GraphSnapshotReference snapshotRef
) {
}
