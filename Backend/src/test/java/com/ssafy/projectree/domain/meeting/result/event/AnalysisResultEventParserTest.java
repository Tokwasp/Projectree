package com.ssafy.projectree.domain.meeting.result.event;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AnalysisResultEventParserTest extends IntegrationTestSupport {

    @Autowired
    private AnalysisResultEventParser parser;

    @Test
    void parsesEnvelopeAndKeepsPayloadAsJsonObject() {
        AnalysisResultEventEnvelope event = parser.parse("""
                {
                  "eventSchemaVersion": 3,
                  "eventId": "8d8cd249-1792-49f4-8734-4fb561e57431",
                  "eventType": "PROJECT_GRAPH_CHANGED",
                  "occurredAt": "2026-08-04T12:30:00Z",
                  "projectId": 1,
                  "meetingId": 2,
                  "commandId": "6b88b593-d153-4e67-b9f4-5b3c4f2dbd7c",
                  "payload": {"revision": 7}
                }
                """);

        assertThat(event.eventType()).isEqualTo(AnalysisResultEventType.PROJECT_GRAPH_CHANGED);
        assertThat(event.payload().isObject()).isTrue();
        assertThat(event.payload().get("revision").asInt()).isEqualTo(7);
    }

    @Test
    void rejectsMalformedOrMissingRequiredJson() {
        assertThatThrownBy(() -> parser.parse("{not-json}"))
                .isInstanceOf(AnalysisResultContractException.class);
        assertThatThrownBy(() -> parser.parse(""))
                .isInstanceOf(AnalysisResultContractException.class);
    }
}
