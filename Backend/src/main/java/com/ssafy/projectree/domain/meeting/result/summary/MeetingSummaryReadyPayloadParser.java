package com.ssafy.projectree.domain.meeting.result.summary;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Component
@RequiredArgsConstructor
public class MeetingSummaryReadyPayloadParser {

    private final ObjectMapper objectMapper;

    public MeetingSummaryReadyPayload parse(JsonNode payload) {
        if (payload == null || !payload.isObject()) {
            throw new AnalysisResultContractException("Meeting summary payload must be a JSON object");
        }
        requireTextField(payload, "meetingSummaryId");
        requireIntegralNumber(payload, "summaryVersion");
        requireTextField(payload, "status");
        requireTextField(payload, "apiPath");
        try {
            return objectMapper.treeToValue(payload, MeetingSummaryReadyPayload.class);
        } catch (JacksonException exception) {
            throw new AnalysisResultContractException("Meeting summary payload is invalid", exception);
        }
    }

    private void requireTextField(JsonNode payload, String fieldName) {
        JsonNode field = payload.get(fieldName);
        if (field == null || !field.isTextual()) {
            throw new AnalysisResultContractException(fieldName + " must be a string");
        }
    }

    private void requireIntegralNumber(JsonNode payload, String fieldName) {
        JsonNode field = payload.get(fieldName);
        if (field == null || !field.isIntegralNumber()) {
            throw new AnalysisResultContractException(fieldName + " must be an integer");
        }
    }
}
