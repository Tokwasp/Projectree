package com.ssafy.projectree.domain.meeting.result.graph.command;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeContentBatchUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.command.NodeContentUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class NodeContentUpdateCommandPayloadParser {

    private final ObjectMapper objectMapper;

    public NodeContentUpdateCommandPayloadParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public ParsedCommand parse(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox outbox
    ) {
        validateOutboxReference(event, outbox);
        int schemaVersion = readSchemaVersion(outbox.getPayload());
        return switch (schemaVersion) {
            case NodeContentUpdateRequestedCommand.CURRENT_SCHEMA_VERSION ->
                    parseV1(event, outbox);
            case NodeContentBatchUpdateRequestedCommand.CURRENT_SCHEMA_VERSION ->
                    parseV2(event, outbox);
            default -> throw contract(
                    "Unsupported node content update command schema version"
            );
        };
    }

    private void validateOutboxReference(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox outbox
    ) {
        if (outbox.getCommandType()
                != MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED
                || outbox.getMeeting() != null
                || outbox.getTargetProjectId() == null
                || !outbox.getTargetProjectId().equals(event.projectId())) {
            throw contract("Node content update command reference does not match");
        }
    }

    private int readSchemaVersion(String payload) {
        try {
            JsonNode commandJson = objectMapper.readTree(payload);
            JsonNode schemaVersion = commandJson == null
                    ? null
                    : commandJson.get("commandSchemaVersion");
            if (schemaVersion == null || !schemaVersion.isIntegralNumber()) {
                throw contract("Node content update command schema version is missing");
            }
            return schemaVersion.intValue();
        } catch (JacksonException exception) {
            throw contract("Node content update command payload is invalid", exception);
        }
    }

    private ParsedCommand parseV1(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox outbox
    ) {
        NodeContentUpdateRequestedCommand command = read(
                outbox.getPayload(), NodeContentUpdateRequestedCommand.class
        );
        if (command == null) {
            throw contract("Node content update V1 command must not be null");
        }
        validateEnvelope(event, outbox, command.commandId(), command.commandType(),
                command.requestedAt(), command.projectId(), command.payload());
        NodeContentUpdateRequestedCommand.Payload payload = command.payload();
        if (outbox.getTargetNodeId() == null
                || outbox.getTargetNodeId().isBlank()
                || !outbox.getTargetNodeId().equals(payload.nodeId())
                || payload.expectedNodeVersion() <= 0
                || payload.requestedByMemberId() <= 0
                || (payload.title() == null && payload.content() == null)) {
            throw contract("Node content update V1 payload fields are invalid");
        }
        return new ParsedCommand(
                NodeContentUpdateRequestedCommand.CURRENT_SCHEMA_VERSION,
                List.of(new RequestedNodeUpdate(
                        payload.nodeId(),
                        payload.expectedNodeVersion(),
                        payload.title(),
                        payload.content()
                ))
        );
    }

    private ParsedCommand parseV2(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox outbox
    ) {
        NodeContentBatchUpdateRequestedCommand command = read(
                outbox.getPayload(), NodeContentBatchUpdateRequestedCommand.class
        );
        if (command == null) {
            throw contract("Node content update V2 command must not be null");
        }
        validateEnvelope(event, outbox, command.commandId(), command.commandType(),
                command.requestedAt(), command.projectId(), command.payload());
        NodeContentBatchUpdateRequestedCommand.Payload payload = command.payload();
        if (outbox.getTargetNodeId() != null
                || payload.requestedByMemberId() <= 0
                || payload.nodes() == null
                || payload.nodes().isEmpty()) {
            throw contract("Node content update V2 payload fields are invalid");
        }

        Set<String> uniqueNodeIds = new HashSet<>();
        List<RequestedNodeUpdate> requestedNodes = payload.nodes().stream()
                .map(node -> validateV2Node(node, uniqueNodeIds))
                .toList();
        return new ParsedCommand(
                NodeContentBatchUpdateRequestedCommand.CURRENT_SCHEMA_VERSION,
                requestedNodes
        );
    }

    private RequestedNodeUpdate validateV2Node(
            NodeContentBatchUpdateRequestedCommand.NodeUpdate node,
            Set<String> uniqueNodeIds
    ) {
        if (node == null
                || node.nodeId() == null
                || node.nodeId().isBlank()
                || !uniqueNodeIds.add(node.nodeId())
                || node.expectedNodeVersion() <= 0
                || node.title() == null
                || node.title().isBlank()
                || node.title().length() > 255) {
            throw contract("Node content update V2 node fields are invalid");
        }
        return new RequestedNodeUpdate(
                node.nodeId(), node.expectedNodeVersion(), node.title(), null
        );
    }

    private void validateEnvelope(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox outbox,
            java.util.UUID commandId,
            MeetingAnalysisCommandType commandType,
            java.time.Instant requestedAt,
            int projectId,
            Object payload
    ) {
        if (commandId == null
                || !outbox.getCommandId().equals(commandId.toString())
                || commandType != MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED
                || requestedAt == null
                || projectId != event.projectId()
                || payload == null) {
            throw contract("Node content update command envelope does not match");
        }
    }

    private <T> T read(String payload, Class<T> commandType) {
        try {
            return objectMapper.readValue(payload, commandType);
        } catch (JacksonException exception) {
            throw contract("Node content update command payload is invalid", exception);
        }
    }

    private AnalysisResultContractException contract(String message) {
        return new AnalysisResultContractException(message);
    }

    private AnalysisResultContractException contract(
            String message,
            JacksonException cause
    ) {
        return new AnalysisResultContractException(message, cause);
    }

    public record ParsedCommand(
            int schemaVersion,
            List<RequestedNodeUpdate> requestedNodes
    ) {
    }

    public record RequestedNodeUpdate(
            String nodeId,
            long expectedNodeVersion,
            String title,
            String content
    ) {
    }
}
