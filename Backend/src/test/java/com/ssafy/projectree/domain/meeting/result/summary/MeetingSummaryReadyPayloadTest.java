package com.ssafy.projectree.domain.meeting.result.summary;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingSummaryReadyPayloadTest extends IntegrationTestSupport {

    @Autowired
    private MeetingSummaryReadyPayloadParser parser;
    @Autowired
    private MeetingSummaryReadyPayloadValidator validator;
    @Autowired
    private ObjectMapper objectMapper;

    @Test
    void parsesAndCanonicalizesValidSummaryPayload() {
        String summaryId = UUID.randomUUID().toString();
        MeetingSummaryReadyPayload payload = validate(payload(summaryId.toUpperCase(), 1, "/api/v1/meetings/7/summary?summaryVersion=1"));

        assertThat(payload.meetingSummaryId()).isEqualTo(summaryId);
        assertThat(payload.summaryVersion()).isEqualTo(1);
        assertThat(payload.status()).isEqualTo(MeetingSummaryResultStatus.READY);
    }

    @Test
    void rejectsInvalidIdVersionStatusAndFieldTypes() {
        assertThatThrownBy(() -> validate(payload("invalid", 1, "/api/v1/meetings/7/summary?summaryVersion=1")))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validate(payload(UUID.randomUUID().toString(), 0, "/api/v1/meetings/7/summary?summaryVersion=0")))
                .isInstanceOf(AnalysisResultContractException.class);

        JsonNode invalidStatus = objectMapper.createObjectNode()
                .put("meetingSummaryId", UUID.randomUUID().toString())
                .put("summaryVersion", 1)
                .put("status", "WRITING")
                .put("apiPath", "/api/v1/meetings/7/summary?summaryVersion=1");
        assertThatThrownBy(() -> parser.parse(invalidStatus))
                .isInstanceOf(AnalysisResultContractException.class);

        JsonNode invalidVersionType = objectMapper.createObjectNode()
                .put("meetingSummaryId", UUID.randomUUID().toString())
                .put("summaryVersion", "1")
                .put("status", "READY")
                .put("apiPath", "/api/v1/meetings/7/summary?summaryVersion=1");
        assertThatThrownBy(() -> parser.parse(invalidVersionType))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    @Test
    void rejectsUnsafeOrInconsistentApiPath() {
        assertThatThrownBy(() -> validate(payload(UUID.randomUUID().toString(), 1, "https://python.example/summary")))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validate(payload(UUID.randomUUID().toString(), 1, "//python.example/summary")))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validate(payload(UUID.randomUUID().toString(), 1, "/api/v1/meetings/7/summary?summaryVersion=1#fragment")))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validate(payload(UUID.randomUUID().toString(), 1, "/api/v1/meetings/8/summary?summaryVersion=1")))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validate(payload(UUID.randomUUID().toString(), 1, "/api/v1/meetings/7/summary?summaryVersion=2")))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> validate(payload(UUID.randomUUID().toString(), 1, "/api/v1/meetings/7/summary?summaryVersion=1&summaryVersion=1")))
                .isInstanceOf(AnalysisResultContractException.class);
    }

    private MeetingSummaryReadyPayload validate(JsonNode payload) {
        return validator.validate(parser.parse(payload), event());
    }

    private JsonNode payload(String summaryId, int version, String apiPath) {
        return objectMapper.createObjectNode()
                .put("meetingSummaryId", summaryId)
                .put("summaryVersion", version)
                .put("status", "READY")
                .put("apiPath", apiPath);
    }

    private AnalysisResultEventEnvelope event() {
        return new AnalysisResultEventEnvelope(
                3, UUID.randomUUID().toString(), AnalysisResultEventType.MEETING_SUMMARY_READY,
                Instant.now(), 1, 7, UUID.randomUUID().toString(), objectMapper.createObjectNode()
        );
    }
}
