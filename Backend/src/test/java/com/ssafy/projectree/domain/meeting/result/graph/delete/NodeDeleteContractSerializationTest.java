package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeDeleteCommandPayload;
import com.ssafy.projectree.domain.meeting.command.NodeDeleteRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventParser;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteStatusResponse;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.validation.AnalysisEventReferenceValidator;
import com.ssafy.projectree.domain.meeting.result.validation.AnalysisEventValidator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

class NodeDeleteContractSerializationTest extends IntegrationTestSupport {

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private AnalysisResultEventParser eventParser;

    @Autowired
    private AnalysisEventValidator envelopeValidator;

    @Autowired
    private AnalysisEventReferenceValidator referenceValidator;

    @Autowired
    private MeetingAnalysisCommandOutboxRepository commandRepository;

    @Test
    void serializesAndDeserializesAllNodeDeleteEnumValuesByName() throws Exception {
        assertEnum(MeetingAnalysisCommandType.NODE_DELETE_REQUESTED);
        assertEnum(GraphResultSourceType.NODE_DELETE);
        assertEnum(AnalysisResultEventType.NODE_DELETE_REJECTED);
        for (NodeDeleteCommandStatus status : NodeDeleteCommandStatus.values()) {
            assertEnum(status);
        }
        for (NodeDeleteItemType itemType : NodeDeleteItemType.values()) {
            assertEnum(itemType);
        }
        for (NodeDeleteRejectionReason reason : NodeDeleteRejectionReason.values()) {
            assertEnum(reason);
        }
    }

    @Test
    void preservesTheExistingCommandEnvelopeAndSchemaVersion() throws Exception {
        long largeVersion = (long) Integer.MAX_VALUE + 10L;
        UUID commandId = UUID.fromString("6aacd404-f36e-48fb-a821-f9f657bd829f");
        NodeDeleteRequestedCommand command = new NodeDeleteRequestedCommand(
                NodeDeleteRequestedCommand.CURRENT_SCHEMA_VERSION,
                commandId,
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                Instant.parse("2026-08-07T01:30:00Z"),
                1,
                new NodeDeleteCommandPayload(
                        List.of("0afdda91-2576-54d3-bb87-8e9263b1d17c"),
                        largeVersion,
                        15
                )
        );

        var json = objectMapper.readTree(objectMapper.writeValueAsString(command));
        assertThat(json.path("commandSchemaVersion").asInt()).isEqualTo(1);
        assertThat(json.path("commandType").asText()).isEqualTo("NODE_DELETE_REQUESTED");
        assertThat(json.path("projectId").asInt()).isEqualTo(1);
        assertThat(json.path("payload").path("expectedGraphVersion").asLong())
                .isEqualTo(largeVersion);
        assertThat(json.path("payload").path("requestedByMemberId").asInt()).isEqualTo(15);

        NodeDeleteRequestedCommand roundTrip = objectMapper.readValue(
                objectMapper.writeValueAsString(command),
                NodeDeleteRequestedCommand.class
        );
        assertThat(roundTrip.payload().expectedGraphVersion()).isEqualTo(largeVersion);
    }

    @Test
    void parsesNodeDeleteRejectedWithTheExistingResultEnvelope() {
        AnalysisResultEventEnvelope event = eventParser.parse("""
                {
                  "eventSchemaVersion": 3,
                  "eventId": "792cbf87-b2ed-4010-a893-beb286597a47",
                  "eventType": "NODE_DELETE_REJECTED",
                  "occurredAt": "2026-08-07T01:30:02Z",
                  "projectId": 1,
                  "meetingId": null,
                  "commandId": "6aacd404-f36e-48fb-a821-f9f657bd829f",
                  "payload": {
                    "sourceType": "NODE_DELETE",
                    "reasonCode": "GRAPH_VERSION_CONFLICT"
                  }
                }
                """);

        assertThat(event.eventSchemaVersion()).isEqualTo(3);
        assertThat(event.eventType()).isEqualTo(AnalysisResultEventType.NODE_DELETE_REJECTED);
        NodeDeleteRejectedPayload payload =
                objectMapper.treeToValue(event.payload(), NodeDeleteRejectedPayload.class);
        assertThat(payload.sourceType()).isEqualTo(GraphResultSourceType.NODE_DELETE);
        assertThat(payload.reasonCode())
                .isEqualTo(NodeDeleteRejectionReason.GRAPH_VERSION_CONFLICT);
    }

    @Test
    void rejectedEventPassesParserEnvelopeAndReferenceValidation() {
        UUID commandId = UUID.randomUUID();
        commandRepository.saveAndFlush(MeetingAnalysisCommandOutbox.pendingNodeDelete(
                commandId,
                1,
                "{\"commandType\":\"NODE_DELETE_REQUESTED\"}",
                15,
                LocalDateTime.now()
        ));
        AnalysisResultEventEnvelope parsed = eventParser.parse("""
                {
                  "eventSchemaVersion": 3,
                  "eventId": "792cbf87-b2ed-4010-a893-beb286597a47",
                  "eventType": "NODE_DELETE_REJECTED",
                  "occurredAt": "2026-08-07T01:30:02Z",
                  "projectId": 1,
                  "meetingId": null,
                  "commandId": "%s",
                  "payload": {
                    "sourceType": "NODE_DELETE",
                    "reasonCode": "GRAPH_VERSION_CONFLICT"
                  }
                }
                """.formatted(commandId));
        AnalysisResultEventEnvelope validated = envelopeValidator.validateEnvelope(parsed);

        assertThatCode(() -> referenceValidator.validateReferences(validated))
                .doesNotThrowAnyException();
    }

    @Test
    void statusResponsePreservesVersionsAboveIntegerRange() {
        long expectedVersion = (long) Integer.MAX_VALUE + 10L;
        long resultVersion = expectedVersion + 1L;
        GraphNodeDeleteStatusResponse response = new GraphNodeDeleteStatusResponse(
                UUID.randomUUID(),
                1,
                List.of("0afdda91-2576-54d3-bb87-8e9263b1d17c"),
                expectedVersion,
                resultVersion,
                NodeDeleteCommandStatus.SUCCEEDED,
                null,
                LocalDateTime.now(),
                LocalDateTime.now()
        );

        assertThat(response.expectedGraphVersion()).isEqualTo(expectedVersion);
        assertThat(response.resultGraphVersion()).isEqualTo(resultVersion);
    }

    private <E extends Enum<E>> void assertEnum(E value) throws Exception {
        String json = objectMapper.writeValueAsString(value);
        assertThat(json).isEqualTo("\"" + value.name() + "\"");
        assertThat(objectMapper.readValue(json, value.getDeclaringClass())).isEqualTo(value);
    }
}
