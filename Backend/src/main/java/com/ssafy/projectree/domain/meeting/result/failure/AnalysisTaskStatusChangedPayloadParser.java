package com.ssafy.projectree.domain.meeting.result.failure;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Component
@RequiredArgsConstructor
public class AnalysisTaskStatusChangedPayloadParser {

    private final ObjectMapper objectMapper;

    public AnalysisTaskStatusChangedPayload parse(JsonNode payload) {
        if (payload == null || !payload.isObject()) {
            throw new AnalysisResultContractException("Analysis task status payload must be a JSON object");
        }
        requireTextField(payload, "taskType");
        requireTextField(payload, "status");
        requireTextField(payload, "failureCode");
        requireTextField(payload, "failureMessage");
        try {
            return objectMapper.treeToValue(payload, AnalysisTaskStatusChangedPayload.class);
        } catch (JacksonException exception) {
            throw new AnalysisResultContractException("Analysis task status payload is invalid", exception);
        }
    }

    private void requireTextField(JsonNode payload, String fieldName) {
        JsonNode field = payload.get(fieldName);
        if (field == null || !field.isTextual()) {
            throw new AnalysisResultContractException(fieldName + " must be a string");
        }
    }
}
