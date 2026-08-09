package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeDeleteCommandPayload;
import com.ssafy.projectree.domain.meeting.command.NodeDeleteRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus;
import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteItemType;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import jakarta.persistence.EntityManager;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class NodeDeleteGraphProjectionApplier {

    private final ProjectRepository projectRepository;
    private final NodeDeleteCommandRepository deleteCommandRepository;
    private final NodeDeleteCommandItemRepository deleteItemRepository;
    private final MeetingAnalysisCommandOutboxRepository outboxRepository;
    private final ProjectNodeProjectionRepository nodeRepository;
    private final ProjectGraphSyncRepository graphSyncRepository;
    private final ResultInboxService resultInboxService;
    private final GraphProjectionReplacer projectionReplacer;
    private final EntityManager entityManager;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final ProjectGraphOperationGuard graphOperationGuard;

    @Transactional
    public GraphProjectionApplyResult apply(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            ProjectGraphSnapshot snapshot
    ) {
        validateInputs(event, payload, snapshot);
        projectRepository.findByIdForUpdate(event.projectId())
                .orElseThrow(() -> contract(
                        "Node delete result project does not exist"
                ));
        NodeDeleteCommand deleteCommand = findPendingCommand(event);
        MeetingAnalysisCommandOutbox outbox = findAndValidateOutbox(
                event,
                deleteCommand
        );
        List<NodeDeleteCommandItem> items = deleteItemRepository
                .findAllByCommandId(deleteCommand.getCommandId());
        validateStoredItems(deleteCommand, items);
        NodeDeleteRequestedCommand requestedCommand =
                parseRequestedCommand(outbox);
        validateRequestedCommand(
                event,
                deleteCommand,
                outbox,
                requestedCommand,
                items
        );

        ProjectGraphSync sync = graphSyncRepository
                .findByProjectIdForUpdate(event.projectId())
                .orElseThrow(() -> new IllegalStateException(
                        "Project graph sync does not exist"
                ));
        validateVersionAndGuard(event, payload, deleteCommand, sync);
        validateCurrentProjectionVersions(event.projectId(), items);
        validateDeletedNodesAbsent(snapshot, items);

        resultInboxService.registerProcessed(event);
        Instant syncedAt = Instant.now(clock);
        entityManager.flush();
        entityManager.clear();
        projectionReplacer.replace(event.projectId(), snapshot, syncedAt);

        sync = graphSyncRepository.findByProjectIdForUpdate(event.projectId())
                .orElseThrow(() -> new IllegalStateException(
                        "Project graph sync disappeared during replacement"
                ));
        deleteCommand = deleteCommandRepository
                .findByProjectIdAndCommandIdForUpdate(
                        event.projectId(),
                        event.commandId()
                )
                .orElseThrow(() -> contract(
                        "Node delete command disappeared during replacement"
                ));
        sync.advanceTo(payload.graphVersion(), event.commandId(), syncedAt);
        deleteCommand.markSucceeded(
                canonicalUuid(event.eventId(), "eventId"),
                payload.graphVersion(),
                LocalDateTime.ofInstant(event.occurredAt(), clock.getZone())
        );
        if (!graphOperationGuard.release(
                sync,
                event.commandId(),
                "GRAPH_PROJECTION_APPLIED"
        )) {
            throw contract(
                    "Node delete result does not own the active graph operation"
            );
        }
        log.info(
                "[AnalysisFlow] NODE_DELETE_RESULT_APPLIED. projectId={}, commandId={}, resultGraphVersion={}, deletedNodeCount={}",
                event.projectId(),
                event.commandId(),
                payload.graphVersion(),
                items.size()
        );
        return new GraphProjectionApplyResult(
                null,
                true,
                payload.graphVersion(),
                sync.getCurrentGraphVersion()
        );
    }

    private void validateInputs(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            ProjectGraphSnapshot snapshot
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(payload, "payload must not be null");
        Objects.requireNonNull(snapshot, "snapshot must not be null");
        if (payload.sourceType() != GraphResultSourceType.NODE_DELETE
                || event.projectId() == null
                || event.projectId() <= 0
                || event.meetingId() != null
                || event.occurredAt() == null) {
            throw contract("Node delete graph result contract does not match");
        }
    }

    private NodeDeleteCommand findPendingCommand(
            AnalysisResultEventEnvelope event
    ) {
        NodeDeleteCommand command = deleteCommandRepository
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
        return command;
    }

    private MeetingAnalysisCommandOutbox findAndValidateOutbox(
            AnalysisResultEventEnvelope event,
            NodeDeleteCommand command
    ) {
        if (command.getOutboxId() == null) {
            throw contract("Node delete command outbox is missing");
        }
        MeetingAnalysisCommandOutbox outbox = outboxRepository
                .findById(command.getOutboxId())
                .orElseThrow(() -> contract(
                        "Node delete command outbox does not exist"
                ));
        if (!command.getCommandId().equals(outbox.getCommandId())
                || !event.commandId().equals(outbox.getCommandId())
                || outbox.getCommandType()
                != MeetingAnalysisCommandType.NODE_DELETE_REQUESTED
                || outbox.getMeeting() != null
                || outbox.getTargetProjectId() == null
                || !outbox.getTargetProjectId().equals(event.projectId())
                || outbox.getTargetNodeId() != null
                || outbox.getRequestedByMemberId()
                != command.getRequestedByMemberId()) {
            throw contract("Node delete command outbox does not match");
        }
        return outbox;
    }

    private void validateStoredItems(
            NodeDeleteCommand command,
            List<NodeDeleteCommandItem> items
    ) {
        Set<String> itemIds = new HashSet<>();
        long requestedCount = 0;
        long mergedSourceCount = 0;
        for (NodeDeleteCommandItem item : items) {
            if (!itemIds.add(item.getNodeId())) {
                throw contract("Node delete command contains duplicate item nodeId");
            }
            if (item.getItemType() == NodeDeleteItemType.REQUESTED) {
                requestedCount++;
            } else if (item.getItemType() == NodeDeleteItemType.MERGED_SOURCE) {
                mergedSourceCount++;
            } else {
                throw contract("Node delete command item type is invalid");
            }
        }
        if (requestedCount != command.getRequestedNodeCount()
                || mergedSourceCount != command.getMergedSourceCount()
                || items.size() != command.getTotalNodeCount()) {
            throw contract("Node delete command item counts do not match");
        }
    }

    private NodeDeleteRequestedCommand parseRequestedCommand(
            MeetingAnalysisCommandOutbox outbox
    ) {
        try {
            return objectMapper.readValue(
                    outbox.getPayload(),
                    NodeDeleteRequestedCommand.class
            );
        } catch (JacksonException exception) {
            throw contract("Node delete command payload is invalid");
        }
    }

    private void validateRequestedCommand(
            AnalysisResultEventEnvelope event,
            NodeDeleteCommand deleteCommand,
            MeetingAnalysisCommandOutbox outbox,
            NodeDeleteRequestedCommand command,
            List<NodeDeleteCommandItem> items
    ) {
        if (command == null
                || command.commandSchemaVersion()
                != NodeDeleteRequestedCommand.CURRENT_SCHEMA_VERSION
                || command.commandId() == null
                || !outbox.getCommandId().equals(command.commandId().toString())
                || command.commandType()
                != MeetingAnalysisCommandType.NODE_DELETE_REQUESTED
                || command.requestedAt() == null
                || command.projectId() != event.projectId()
                || command.payload() == null) {
            throw contract("Node delete command envelope does not match");
        }
        NodeDeleteCommandPayload requested = command.payload();
        if (requested.expectedGraphVersion()
                != deleteCommand.getExpectedGraphVersion()
                || requested.requestedByMemberId()
                != deleteCommand.getRequestedByMemberId()
                || requested.nodeIds() == null) {
            throw contract("Node delete command payload fields do not match");
        }
        Set<String> payloadIds = new HashSet<>(requested.nodeIds());
        Set<String> storedRequestedIds = items.stream()
                .filter(item -> item.getItemType() == NodeDeleteItemType.REQUESTED)
                .map(NodeDeleteCommandItem::getNodeId)
                .collect(java.util.stream.Collectors.toSet());
        if (payloadIds.size() != requested.nodeIds().size()
                || !payloadIds.equals(storedRequestedIds)) {
            throw contract(
                    "Node delete command requested node IDs do not match stored items"
            );
        }
    }

    private void validateVersionAndGuard(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            NodeDeleteCommand command,
            ProjectGraphSync sync
    ) {
        long expectedResultVersion;
        try {
            expectedResultVersion = Math.addExact(
                    command.getExpectedGraphVersion(),
                    1
            );
        } catch (ArithmeticException exception) {
            throw contract("Node delete expected graph version cannot advance");
        }
        if (sync.getCurrentGraphVersion() != command.getExpectedGraphVersion()
                || payload.graphVersion() != expectedResultVersion) {
            throw contract("Node delete result graphVersion is invalid");
        }
        if (!sync.hasActiveCommand()
                || !event.commandId().equals(sync.getActiveCommandId())
                || sync.getActiveCommandType()
                != MeetingAnalysisCommandType.NODE_DELETE_REQUESTED) {
            throw contract(
                    "Node delete result does not own the active graph operation"
            );
        }
    }

    private void validateCurrentProjectionVersions(
            int projectId,
            List<NodeDeleteCommandItem> items
    ) {
        Map<String, ProjectNodeProjection> currentNodes = new HashMap<>();
        for (ProjectNodeProjection node : nodeRepository.findAllByProjectId(projectId)) {
            currentNodes.put(node.getNodeId(), node);
        }
        for (NodeDeleteCommandItem item : items) {
            ProjectNodeProjection node = currentNodes.get(item.getNodeId());
            if (node == null
                    || node.getSourceNodeVersion() != item.getExpectedNodeVersion()) {
                throw contract(
                        "Node delete item does not match the current projection"
                );
            }
        }
    }

    private void validateDeletedNodesAbsent(
            ProjectGraphSnapshot snapshot,
            List<NodeDeleteCommandItem> items
    ) {
        Set<String> snapshotNodeIds = snapshot.nodes().stream()
                .map(node -> node.nodeId())
                .collect(java.util.stream.Collectors.toSet());
        for (NodeDeleteCommandItem item : items) {
            if (snapshotNodeIds.contains(item.getNodeId())) {
                throw contract(
                        "Node delete result snapshot still contains a deleted node"
                );
            }
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
