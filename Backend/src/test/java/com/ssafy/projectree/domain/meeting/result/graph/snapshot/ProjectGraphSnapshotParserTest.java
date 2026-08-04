package com.ssafy.projectree.domain.meeting.result.graph.snapshot;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.MapperFeature;
import tools.jackson.databind.ObjectMapper;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProjectGraphSnapshotParserTest extends IntegrationTestSupport {

    @Autowired
    private ProjectGraphSnapshotParser parser;
    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void parsesValidSnapshotWithoutMutatingSharedObjectMapper() {
        ProjectGraphSnapshot snapshot = parser.parse(json("[]").getBytes(StandardCharsets.UTF_8));

        assertThat(snapshot.projectId()).isEqualTo(1);
        assertThat(snapshot.mergeRecords()).isEmpty();
        assertThat(objectMapper.isEnabled(MapperFeature.ALLOW_COERCION_OF_SCALARS)).isTrue();
    }

    @Test
    void rejectsUnknownFieldsLifecycleStatusAndScalarCoercion() {
        assertContractFailure(json("[]").replace("\"projectId\":1", "\"projectId\":\"1\""));
        assertContractFailure(json("[]").replace("\"meetingId\":1", "\"meetingId\":1.0"));
        assertContractFailure(json("[]").replace("\"nodes\":[]", "\"unknownField\":true,\"nodes\":[]"));
        assertContractFailure(json("[]").replace("\"nodes\":[]", "\"nodes\":[{\"nodeId\":\""
                + UUID.randomUUID() + "\",\"lifecycleStatus\":\"TODO\"}]"));
        assertContractFailure(json("[]").replace("\"nodes\":[]", "\"nodes\":[{\"nodeType\":1}]"));
        assertContractFailure(json("[]").replace("\"evidences\":[]", "\"evidences\":[{\"unknownEvidence\":true}]"));
    }

    @Test
    void rejectsDuplicateKeysTrailingTokensAndMalformedUtf8() {
        assertContractFailure(json("[]").replace("\"projectId\":1", "\"projectId\":1,\"projectId\":2"));
        assertContractFailure(json("[]") + " {}");
        assertThatThrownBy(() -> parser.parse(new byte[]{(byte) 0xC3, (byte) 0x28}))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    @Test
    void acceptsMergeRecordObjectsButRejectsNullRecords() {
        assertThat(parser.parse(json("[{\"mergeId\":\"ignored\"}]").getBytes(StandardCharsets.UTF_8))
                .mergeRecords()).hasSize(1);
        assertContractFailure(json("null"));
        assertContractFailure(json("[null]"));
    }

    private void assertContractFailure(String json) {
        assertThatThrownBy(() -> parser.parse(json.getBytes(StandardCharsets.UTF_8)))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    private String json(String mergeRecords) {
        return """
                {"snapshotSchemaVersion":1,"projectId":1,"meetingId":1,
                "commandId":"%s","graphVersion":1,"generatedAt":"2026-08-04T12:30:00Z",
                "nodes":[],"evidences":[],"mergeRecords":%s}
                """.formatted(UUID.randomUUID(), mergeRecords).replaceAll("\\s+", "");
    }
}
