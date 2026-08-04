package com.ssafy.projectree.domain.meeting.result.graph.event;

import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

@Component
@RequiredArgsConstructor
public class ProjectGraphChangedPayloadParser {

    private final ObjectMapper objectMapper;

    public ProjectGraphChangedPayload parse(JsonNode payload) {
        if (payload == null || !payload.isObject()) {
            throw new AnalysisResultContractException("Project graph payload must be a JSON object");
        }
        requireText(payload, "sourceType");
        requireIntegralNumber(payload, "graphVersion");
        JsonNode snapshotRef = payload.get("snapshotRef");
        if (snapshotRef == null || !snapshotRef.isObject()) {
            throw new AnalysisResultContractException("snapshotRef must be a JSON object");
        }
        requireText(snapshotRef, "bucket");
        requireText(snapshotRef, "objectKey");
        requireText(snapshotRef, "contentType");
        requireIntegralNumber(snapshotRef, "sizeBytes");
        requireText(snapshotRef, "sha256");
        try {
            return objectMapper.treeToValue(payload, ProjectGraphChangedPayload.class);
        } catch (JacksonException exception) {
            throw new AnalysisResultContractException("Project graph payload is invalid", exception);
        }
    }

    private void requireText(JsonNode object, String fieldName) {
        JsonNode field = object.get(fieldName);
        if (field == null || !field.isTextual()) {
            throw new AnalysisResultContractException(fieldName + " must be a string");
        }
    }

    private void requireIntegralNumber(JsonNode object, String fieldName) {
        JsonNode field = object.get(fieldName);
        if (field == null || !field.isIntegralNumber()) {
            throw new AnalysisResultContractException(fieldName + " must be an integer");
        }
    }
}
