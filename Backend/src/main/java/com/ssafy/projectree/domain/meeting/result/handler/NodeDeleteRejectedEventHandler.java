package com.ssafy.projectree.domain.meeting.result.handler;

import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventType;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus;
import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteRejectedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
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

import java.time.Clock;
import java.time.LocalDateTime;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class NodeDeleteRejectedEventHandler implements AnalysisResultEventHandler {

    private final ObjectMapper objectMapper;
    private final ProjectRepository projectRepository;
    private final NodeDeleteCommandRepository commandRepository;
    private final ResultInboxService resultInboxService;
    private final ProjectGraphOperationGuard graphOperationGuard;
    private final Clock clock;

    @Override
    public AnalysisResultEventType supportedType() {
        return AnalysisResultEventType.NODE_DELETE_REJECTED;
    }

    @Override
    @Transactional
    public void handle(AnalysisResultEventEnvelope event) {
        NodeDeleteRejectedPayload payload = parsePayload(event.payload());
        validateEvent(event, payload);
        projectRepository.findByIdForUpdate(event.projectId())
                .orElseThrow(() -> contract("Node delete result project does not exist"));
        NodeDeleteCommand command = commandRepository
                .findByProjectIdAndCommandIdForUpdate(
                        event.projectId(),
                        event.commandId()
                )
                .orElseThrow(() -> contract(
                        "Node delete command does not exist"
                ));
        if (command.getStatus() != NodeDeleteCommandStatus.PENDING) {
            throw contract("Node delete command must be pending");
        }

        resultInboxService.registerProcessed(event);
        command.markRejected(
                canonicalUuid(event.eventId(), "eventId"),
                payload.reasonCode().name(),
                LocalDateTime.ofInstant(event.occurredAt(), clock.getZone())
        );
        if (!graphOperationGuard.release(
                event.projectId(),
                event.commandId(),
                "NODE_DELETE_REJECTED"
        )) {
            throw contract(
                    "Node delete rejection does not own the active graph operation"
            );
        }
        log.info(
                "[AnalysisFlow] NODE_DELETE_REJECTED_APPLIED. projectId={}, commandId={}, reasonCode={}",
                event.projectId(),
                event.commandId(),
                payload.reasonCode()
        );
    }

    private NodeDeleteRejectedPayload parsePayload(JsonNode payload) {
        if (payload == null || !payload.isObject()) {
            throw contract("Node delete rejected payload must be a JSON object");
        }
        requireText(payload, "sourceType");
        requireText(payload, "reasonCode");
        try {
            return objectMapper.treeToValue(
                    payload,
                    NodeDeleteRejectedPayload.class
            );
        } catch (JacksonException exception) {
            throw new AnalysisResultContractException(
                    "Node delete rejected payload is invalid",
                    exception
            );
        }
    }

    private void validateEvent(
            AnalysisResultEventEnvelope event,
            NodeDeleteRejectedPayload payload
    ) {
        if (event == null
                || event.eventType() != AnalysisResultEventType.NODE_DELETE_REJECTED
                || event.projectId() == null
                || event.projectId() <= 0
                || event.meetingId() != null
                || event.occurredAt() == null
                || payload == null
                || payload.sourceType() != GraphResultSourceType.NODE_DELETE
                || payload.reasonCode() == null) {
            throw contract("Node delete rejected event contract does not match");
        }
    }

    private void requireText(JsonNode payload, String fieldName) {
        JsonNode field = payload.get(fieldName);
        if (field == null || !field.isTextual()) {
            throw contract(fieldName + " must be a string");
        }
    }

    private UUID canonicalUuid(String value, String fieldName) {
        try {
            UUID parsed = UUID.fromString(value);
            if (!parsed.toString().equalsIgnoreCase(value)) {
                throw contract(fieldName + " must be a canonical UUID");
            }
            return parsed;
        } catch (IllegalArgumentException exception) {
            throw contract(fieldName + " must be a canonical UUID");
        }
    }

    private AnalysisResultContractException contract(String message) {
        return new AnalysisResultContractException(message);
    }
}
