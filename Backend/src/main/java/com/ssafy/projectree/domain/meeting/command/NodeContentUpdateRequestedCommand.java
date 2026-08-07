package com.ssafy.projectree.domain.meeting.command;

import java.time.Instant;
import java.util.UUID;

public record NodeContentUpdateRequestedCommand(
        int commandSchemaVersion,
        UUID commandId,
        MeetingAnalysisCommandType commandType,
        Instant requestedAt,
        int projectId,
        Payload payload
) {

    public static final int CURRENT_SCHEMA_VERSION = 1;

    public record Payload(
            String nodeId,
            long expectedNodeVersion,
            String title,
            String content,
            int requestedByMemberId
    ) {
    }
}
