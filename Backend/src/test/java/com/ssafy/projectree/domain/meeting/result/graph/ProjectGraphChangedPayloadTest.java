package com.ssafy.projectree.domain.meeting.result.graph;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayloadParser;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayloadValidator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProjectGraphChangedPayloadTest extends IntegrationTestSupport {

    @Autowired
    private ProjectGraphChangedPayloadParser parser;
    @Autowired
    private ProjectGraphChangedPayloadValidator validator;
    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void acceptsOnlyTheMeetingAnalysisSnapshotContract() {
        ProjectGraphChangedPayload payload = parser.parse(validPayload());
        validator.validate(payload);

        assertThat(payload.graphVersion()).isEqualTo(3L);
        assertThat(payload.snapshotRef().sha256()).hasSize(64);
    }

    @Test
    void rejectsUnsafeReferenceAndInvalidFieldTypes() {
        JsonNode unsafeBucket = validPayload();
        ((tools.jackson.databind.node.ObjectNode) unsafeBucket.path("snapshotRef"))
                .put("bucket", "s3://projectree-graph");
        assertThatThrownBy(() -> validator.validate(parser.parse(unsafeBucket)))
                .isInstanceOf(AnalysisResultContractException.class);

        JsonNode unsafeObjectKey = validPayload();
        ((tools.jackson.databind.node.ObjectNode) unsafeObjectKey.path("snapshotRef"))
                .put("objectKey", "snapshots/../graph.json");
        assertThatThrownBy(() -> validator.validate(parser.parse(unsafeObjectKey)))
                .isInstanceOf(AnalysisResultContractException.class);

        JsonNode invalidSizeType = validPayload();
        ((tools.jackson.databind.node.ObjectNode) invalidSizeType.path("snapshotRef"))
                .put("sizeBytes", "12");
        assertThatThrownBy(() -> parser.parse(invalidSizeType))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    private JsonNode validPayload() {
        return objectMapper.createObjectNode()
                .put("sourceType", "MEETING_ANALYSIS")
                .put("graphVersion", 3)
                .set("snapshotRef", objectMapper.createObjectNode()
                        .put("bucket", "projectree-graph")
                        .put("objectKey", "graphs/" + UUID.randomUUID() + ".json")
                        .put("contentType", "application/json")
                        .put("sizeBytes", 1024)
                        .put("sha256", "a".repeat(64)));
    }
}
