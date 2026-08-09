package com.ssafy.projectree.domain.meeting.result.graph.snapshot;

import tools.jackson.databind.JsonNode;

import java.time.Instant;
import java.util.List;

public record ProjectGraphSnapshot(
        int snapshotSchemaVersion,
        int projectId,
        Integer meetingId,
        String commandId,
        long graphVersion,
        Instant generatedAt,
        List<ProjectGraphSnapshotNode> nodes,
        List<ProjectGraphSnapshotEvidence> evidences,
        List<JsonNode> mergeRecords
) {
}
