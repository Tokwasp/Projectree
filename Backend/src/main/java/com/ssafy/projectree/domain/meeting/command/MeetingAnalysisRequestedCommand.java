package com.ssafy.projectree.domain.meeting.command;

import java.time.Instant;
import java.util.UUID;

public record MeetingAnalysisRequestedCommand(
        int commandSchemaVersion,
        UUID commandId,
        MeetingAnalysisCommandType commandType,
        Instant requestedAt,
        int projectId,
        Payload payload
) {

    public static final int CURRENT_SCHEMA_VERSION = 1;

    public record Payload(
            int meetingId,
            String roomName,
            boolean generateSummary,
            boolean generateNodes
    ) {
    }
}
