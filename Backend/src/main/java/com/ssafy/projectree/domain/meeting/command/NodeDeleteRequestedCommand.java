package com.ssafy.projectree.domain.meeting.command;

import java.time.Instant;
import java.util.UUID;

public record NodeDeleteRequestedCommand(
        int commandSchemaVersion,
        UUID commandId,
        MeetingAnalysisCommandType commandType,
        Instant requestedAt,
        int projectId,
        NodeDeleteCommandPayload payload
) {

    public static final int CURRENT_SCHEMA_VERSION = 1;
}
