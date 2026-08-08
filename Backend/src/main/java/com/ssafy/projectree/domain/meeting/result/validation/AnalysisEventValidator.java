package com.ssafy.projectree.domain.meeting.result.validation;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import org.springframework.stereotype.Component;

import java.util.UUID;

@Component
public class AnalysisEventValidator {

    public static final int SUPPORTED_SCHEMA_VERSION = 3;

    public AnalysisResultEventEnvelope validateEnvelope(AnalysisResultEventEnvelope event) {
        if (event == null) {
            throw new AnalysisResultContractException("Analysis result event must not be null");
        }
        if (event.eventSchemaVersion() != SUPPORTED_SCHEMA_VERSION) {
            throw new AnalysisResultContractException("Unsupported analysis result event schema version");
        }
        if (event.eventType() == null) {
            throw new AnalysisResultContractException("Analysis result event type must not be null");
        }
        if (event.occurredAt() == null) {
            throw new AnalysisResultContractException("Analysis result occurredAt must not be null");
        }
        if (!isPositive(event.projectId())) {
            throw new AnalysisResultContractException("Analysis result projectId must be positive");
        }
        if (event.meetingId() != null && !isPositive(event.meetingId())) {
            throw new AnalysisResultContractException("Analysis result meetingId must be positive when present");
        }
        if (requiresMeetingId(event.eventType()) && event.meetingId() == null) {
            throw new AnalysisResultContractException("Analysis result meetingId is required");
        }
        if (event.payload() == null || !event.payload().isObject()) {
            throw new AnalysisResultContractException("Analysis result payload must be a JSON object");
        }

        return new AnalysisResultEventEnvelope(
                event.eventSchemaVersion(),
                canonicalUuid(event.eventId(), "eventId"),
                event.eventType(),
                event.occurredAt(),
                event.projectId(),
                event.meetingId(),
                canonicalUuid(event.commandId(), "commandId"),
                event.payload()
        );
    }

    private static boolean isPositive(Integer value) {
        return value != null && value > 0;
    }

    private static boolean requiresMeetingId(AnalysisResultEventType eventType) {
        return switch (eventType) {
            case MEETING_SUMMARY_READY, ANALYSIS_TASK_STATUS_CHANGED -> true;
            case PROJECT_GRAPH_CHANGED, NODE_DELETE_REJECTED -> false;
        };
    }

    private static String canonicalUuid(String value, String fieldName) {
        if (value == null || value.isBlank()) {
            throw new AnalysisResultContractException(fieldName + " must not be blank");
        }
        try {
            UUID parsed = UUID.fromString(value);
            if (!parsed.toString().equalsIgnoreCase(value)) {
                throw new AnalysisResultContractException(fieldName + " must be a canonical UUID");
            }
            return parsed.toString();
        } catch (IllegalArgumentException exception) {
            throw new AnalysisResultContractException(fieldName + " must be a canonical UUID", exception);
        }
    }
}
