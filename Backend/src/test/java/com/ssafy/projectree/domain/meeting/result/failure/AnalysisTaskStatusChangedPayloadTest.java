package com.ssafy.projectree.domain.meeting.result.failure;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AnalysisTaskStatusChangedPayloadTest extends IntegrationTestSupport {

    @Autowired
    private AnalysisTaskStatusChangedPayloadParser parser;
    @Autowired
    private AnalysisTaskStatusChangedPayloadValidator validator;
    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void parsesSummaryAndNodesFailurePayloads() {
        AnalysisTaskStatusChangedPayload summary = parse("SUMMARY");
        AnalysisTaskStatusChangedPayload nodes = parse("NODES");

        assertThat(summary.taskType()).isEqualTo(AnalysisTaskType.SUMMARY);
        assertThat(nodes.taskType()).isEqualTo(AnalysisTaskType.NODES);
        assertThat(summary.status()).isEqualTo(AnalysisTaskResultStatus.FAILED);
    }

    @Test
    void rejectsMissingUnknownAndNonFailedTaskContract() {
        assertThatThrownBy(() -> parser.parse(objectMapper.createObjectNode()))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> parse("UNKNOWN"))
                .isInstanceOf(AnalysisResultContractException.class);
        JsonNode nonFailedStatus = objectMapper.createObjectNode()
                .put("taskType", "SUMMARY")
                .put("status", "SUCCEEDED")
                .put("failureCode", "CODE")
                .put("failureMessage", "message");
        assertThatThrownBy(() -> parser.parse(nonFailedStatus))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validator.validate(new AnalysisTaskStatusChangedPayload(
                AnalysisTaskType.SUMMARY, null, "CODE", "message"
        ))).isInstanceOf(AnalysisResultContractException.class);
    }

    @Test
    void rejectsBlankOverlongAndNonTextFailureFields() {
        assertThatThrownBy(() -> validator.validate(new AnalysisTaskStatusChangedPayload(
                AnalysisTaskType.SUMMARY, AnalysisTaskResultStatus.FAILED, " ", "message"
        ))).isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validator.validate(new AnalysisTaskStatusChangedPayload(
                AnalysisTaskType.SUMMARY, AnalysisTaskResultStatus.FAILED, "CODE", " "
        ))).isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validator.validate(new AnalysisTaskStatusChangedPayload(
                AnalysisTaskType.SUMMARY, AnalysisTaskResultStatus.FAILED, "x".repeat(101), "message"
        ))).isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validator.validate(new AnalysisTaskStatusChangedPayload(
                AnalysisTaskType.SUMMARY, AnalysisTaskResultStatus.FAILED, "CODE", "x".repeat(1001)
        ))).isInstanceOf(AnalysisResultContractException.class);

        JsonNode wrongType = objectMapper.createObjectNode()
                .put("taskType", "SUMMARY")
                .put("status", "FAILED")
                .put("failureCode", 7)
                .put("failureMessage", "message");
        assertThatThrownBy(() -> parser.parse(wrongType))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> parser.parse(objectMapper.createArrayNode()))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    private AnalysisTaskStatusChangedPayload parse(String taskType) {
        JsonNode payload = objectMapper.createObjectNode()
                .put("taskType", taskType)
                .put("status", "FAILED")
                .put("failureCode", "GRAPH_ANALYSIS_FAILED")
                .put("failureMessage", "Node analysis failed after retries");
        AnalysisTaskStatusChangedPayload result = parser.parse(payload);
        validator.validate(result);
        return result;
    }
}
