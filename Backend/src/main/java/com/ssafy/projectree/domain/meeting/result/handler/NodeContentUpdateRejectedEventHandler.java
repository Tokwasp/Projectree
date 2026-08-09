package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.command.NodeContentUpdateCommandPayloadParser;
import com.ssafy.projectree.domain.meeting.result.graph.command.NodeContentUpdateCommandPayloadParser.ParsedCommand;
import com.ssafy.projectree.domain.meeting.result.graph.command.NodeContentUpdateRejectedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class NodeContentUpdateRejectedEventHandler implements AnalysisResultEventHandler {

    private final ObjectMapper objectMapper;
    private final ProjectRepository projectRepository;
    private final MeetingAnalysisCommandOutboxRepository commandRepository;
    private final ResultInboxService resultInboxService;
    private final ProjectGraphOperationGuard graphOperationGuard;

    @Override
    public AnalysisResultEventType supportedType() {
        return AnalysisResultEventType.NODE_CONTENT_UPDATE_REJECTED;
    }

    @Override
    @Transactional
    public void handle(AnalysisResultEventEnvelope event) {
        NodeContentUpdateRejectedPayload payload = parsePayload(event.payload());
        validateEvent(event, payload);
        projectRepository.findByIdForUpdate(event.projectId())
                .orElseThrow(() -> contract(
                        "Node content update result project does not exist"
                ));
        MeetingAnalysisCommandOutbox command = commandRepository
                .findByCommandId(event.commandId())
                .orElseThrow(() -> contract(
                        "Node content update command does not exist"
                ));
        ParsedCommand parsedCommand =
                new NodeContentUpdateCommandPayloadParser(objectMapper)
                        .parse(event, command);
        validateFailedNodeReference(payload, parsedCommand);

        resultInboxService.registerProcessed(event);
        if (!graphOperationGuard.release(
                event.projectId(),
                event.commandId(),
                "NODE_CONTENT_UPDATE_REJECTED"
        )) {
            throw contract(
                    "Node content update rejection does not own the active graph operation"
            );
        }
        log.info(
                "[AnalysisFlow] NODE_CONTENT_UPDATE_REJECTED_APPLIED. projectId={}, commandId={}, reasonCode={}, failedNodeId={}",
                event.projectId(),
                event.commandId(),
                payload.reasonCode(),
                payload.failedNodeId()
        );
    }

    private NodeContentUpdateRejectedPayload parsePayload(JsonNode payload) {
        if (payload == null || !payload.isObject()) {
            throw contract("Node content update rejected payload must be a JSON object");
        }
        requireText(payload, "sourceType");
        requireText(payload, "reasonCode");
        JsonNode failedNodeId = payload.get("failedNodeId");
        if (failedNodeId != null
                && !failedNodeId.isNull()
                && !failedNodeId.isTextual()) {
            throw contract("failedNodeId must be a string or null");
        }
        try {
            return objectMapper.treeToValue(
                    payload,
                    NodeContentUpdateRejectedPayload.class
            );
        } catch (JacksonException exception) {
            throw new AnalysisResultContractException(
                    "Node content update rejected payload is invalid",
                    exception
            );
        }
    }

    private void validateEvent(
            AnalysisResultEventEnvelope event,
            NodeContentUpdateRejectedPayload payload
    ) {
        if (event == null
                || event.eventType()
                != AnalysisResultEventType.NODE_CONTENT_UPDATE_REJECTED
                || event.projectId() == null
                || event.projectId() <= 0
                || event.meetingId() != null
                || event.occurredAt() == null
                || payload == null
                || payload.sourceType() != GraphResultSourceType.NODE_CONTENT_UPDATE
                || payload.reasonCode() == null) {
            throw contract("Node content update rejected event contract does not match");
        }
        if (payload.reasonCode().requiresFailedNodeId()
                && !isCanonicalUuid(payload.failedNodeId())) {
            throw contract("failedNodeId is required for node-specific rejection");
        }
        if (payload.failedNodeId() != null
                && !isCanonicalUuid(payload.failedNodeId())) {
            throw contract("failedNodeId must be a canonical UUID");
        }
    }

    private void validateFailedNodeReference(
            NodeContentUpdateRejectedPayload payload,
            ParsedCommand parsedCommand
    ) {
        if (payload.failedNodeId() == null) {
            return;
        }
        boolean failedNodeWasRequested = parsedCommand.requestedNodes().stream()
                .anyMatch(node -> node.nodeId().equals(payload.failedNodeId()));
        if (!failedNodeWasRequested) {
            throw contract("Rejected node was not requested by the command");
        }
    }

    private void requireText(JsonNode payload, String fieldName) {
        JsonNode field = payload.get(fieldName);
        if (field == null || !field.isTextual()) {
            throw contract(fieldName + " must be a string");
        }
    }

    private boolean isCanonicalUuid(String value) {
        try {
            return value != null
                    && UUID.fromString(value).toString().equalsIgnoreCase(value);
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private AnalysisResultContractException contract(String message) {
        return new AnalysisResultContractException(message);
    }
}
