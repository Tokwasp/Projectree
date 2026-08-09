package com.ssafy.projectree.domain.meeting.command;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

public record NodeContentBatchUpdateRequestedCommand(
        int commandSchemaVersion,
        UUID commandId,
        MeetingAnalysisCommandType commandType,
        Instant requestedAt,
        int projectId,
        Payload payload
) {

    public static final int CURRENT_SCHEMA_VERSION = 2;

    public record Payload(List<NodeUpdate> nodes, int requestedByMemberId) {
    }

    public record NodeUpdate(
            String nodeId,
            long expectedNodeVersion,
            String title
    ) {
    }
}
