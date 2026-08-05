package com.ssafy.projectree.domain.meeting.result.validation;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import org.junit.jupiter.api.Test;
import tools.jackson.databind.json.JsonMapper;

import java.time.Instant;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AnalysisEventValidatorTest {

    private final AnalysisEventValidator validator = new AnalysisEventValidator();
    private final JsonMapper objectMapper = JsonMapper.builder().build();

    @Test
    void acceptsCanonicalUppercaseIdsAndNormalizesThemToLowercase() {
        String eventId = UUID.randomUUID().toString();
        String commandId = UUID.randomUUID().toString();

        AnalysisResultEventEnvelope normalized = validator.validateEnvelope(event(
                eventId.toUpperCase(), commandId.toUpperCase(), objectMapper.createObjectNode()
        ));

        assertThat(normalized.eventId()).isEqualTo(eventId);
        assertThat(normalized.commandId()).isEqualTo(commandId);
    }

    @Test
    void rejectsInvalidCommonContractFields() {
        assertThatThrownBy(() -> validator.validateEnvelope(event(
                UUID.randomUUID().toString().replace("-", ""), UUID.randomUUID().toString(),
                objectMapper.createObjectNode()
        ))).isInstanceOf(AnalysisResultContractException.class);

        assertThatThrownBy(() -> validator.validateEnvelope(new AnalysisResultEventEnvelope(
                2, UUID.randomUUID().toString(), AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.now(), 1, 1, UUID.randomUUID().toString(), objectMapper.createObjectNode()
        ))).isInstanceOf(AnalysisResultContractException.class);

        assertThatThrownBy(() -> validator.validateEnvelope(event(
                UUID.randomUUID().toString(), UUID.randomUUID().toString(), objectMapper.createArrayNode()
        ))).isInstanceOf(AnalysisResultContractException.class);
    }

    private AnalysisResultEventEnvelope event(String eventId, String commandId, tools.jackson.databind.JsonNode payload) {
        return new AnalysisResultEventEnvelope(
                3,
                eventId,
                AnalysisResultEventType.PROJECT_GRAPH_CHANGED,
                Instant.parse("2026-08-04T12:30:00Z"),
                1,
                2,
                commandId,
                payload
        );
    }
}
