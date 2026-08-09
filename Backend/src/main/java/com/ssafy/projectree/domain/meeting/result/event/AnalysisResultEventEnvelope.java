package com.ssafy.projectree.domain.meeting.result.event;

import tools.jackson.databind.JsonNode;

import java.time.Instant;

public record AnalysisResultEventEnvelope(
        int eventSchemaVersion,
        String eventId,
        AnalysisResultEventType eventType,
        Instant occurredAt,
        Integer projectId,
        Integer meetingId,
        String commandId,
        JsonNode payload
) {
}
