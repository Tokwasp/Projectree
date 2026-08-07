package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeContentUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshot;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.domain.meeting.result.inbox.service.ResultInboxService;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import jakarta.persistence.EntityManager;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.util.Objects;

@Service
@RequiredArgsConstructor
public class NodeContentUpdateGraphProjectionApplier {

    private final ProjectRepository projectRepository;
    private final MeetingAnalysisCommandOutboxRepository commandRepository;
    private final ProjectGraphSyncRepository graphSyncRepository;
    private final ResultInboxService resultInboxService;
    private final GraphProjectionReplacer projectionReplacer;
    private final EntityManager entityManager;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Transactional
    public GraphProjectionApplyResult apply(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            ProjectGraphSnapshot snapshot
    ) {
        Objects.requireNonNull(event, "event must not be null");
        Objects.requireNonNull(payload, "payload must not be null");
        Objects.requireNonNull(snapshot, "snapshot must not be null");
        if (payload.sourceType() != GraphResultSourceType.NODE_CONTENT_UPDATE) {
            throw contract("Graph result sourceType does not match node content update");
        }

        projectRepository.findByIdForUpdate(event.projectId())
                .orElseThrow(() -> contract("Analysis result project does not exist"));
        MeetingAnalysisCommandOutbox command = commandRepository.findByCommandId(event.commandId())
                .orElseThrow(() -> contract("Analysis result command does not exist"));
        validateCommand(event, command);
        NodeContentUpdateRequestedCommand commandPayload = parseCommandPayload(command);
        validateCommandPayload(event, command, commandPayload);

        ProjectGraphSync sync = graphSyncRepository.findByProjectIdForUpdate(event.projectId())
                .orElseGet(() -> graphSyncRepository.saveAndFlush(
                        ProjectGraphSync.initial(event.projectId(), Instant.now(clock))
                ));
        resultInboxService.registerProcessed(event);

        boolean projectionUpdated = payload.graphVersion() > sync.getCurrentGraphVersion();
        if (projectionUpdated) {
            validateUpdatedNode(command, commandPayload, snapshot);
            Instant syncedAt = Instant.now(clock);
            entityManager.flush();
            entityManager.clear();
            projectionReplacer.replace(event.projectId(), snapshot, syncedAt);
            sync = graphSyncRepository.findByProjectIdForUpdate(event.projectId())
                    .orElseThrow(() -> new IllegalStateException(
                            "Project graph sync disappeared during replacement"
                    ));
            sync.advanceTo(payload.graphVersion(), command.getCommandId(), syncedAt);
        }
        return new GraphProjectionApplyResult(
                null,
                projectionUpdated,
                payload.graphVersion(),
                sync.getCurrentGraphVersion()
        );
    }

    private void validateCommand(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox command
    ) {
        if (command.getCommandType() != MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED) {
            throw contract("Graph result sourceType and command type do not match");
        }
        if (command.getMeeting() != null) {
            throw contract("Node content update command meeting must be null");
        }
        if (command.getTargetProjectId() == null
                || !command.getTargetProjectId().equals(event.projectId())) {
            throw contract("Node content update command project does not match");
        }
        if (command.getTargetNodeId() == null || command.getTargetNodeId().isBlank()) {
            throw contract("Node content update command target node is missing");
        }
    }

    private NodeContentUpdateRequestedCommand parseCommandPayload(
            MeetingAnalysisCommandOutbox command
    ) {
        try {
            return objectMapper.readValue(
                    command.getPayload(),
                    NodeContentUpdateRequestedCommand.class
            );
        } catch (JacksonException exception) {
            throw contract("Node content update command payload is invalid");
        }
    }

    private void validateCommandPayload(
            AnalysisResultEventEnvelope event,
            MeetingAnalysisCommandOutbox command,
            NodeContentUpdateRequestedCommand commandPayload
    ) {
        if (commandPayload == null
                || commandPayload.commandSchemaVersion()
                != NodeContentUpdateRequestedCommand.CURRENT_SCHEMA_VERSION
                || commandPayload.commandId() == null
                || !command.getCommandId().equals(commandPayload.commandId().toString())
                || commandPayload.commandType()
                != MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED
                || commandPayload.projectId() != event.projectId()
                || commandPayload.requestedAt() == null
                || commandPayload.payload() == null) {
            throw contract("Node content update command envelope does not match");
        }

        NodeContentUpdateRequestedCommand.Payload requested = commandPayload.payload();
        if (!command.getTargetNodeId().equals(requested.nodeId())) {
            throw contract("Node content update command target node does not match");
        }
        if (requested.expectedNodeVersion() <= 0
                || requested.requestedByMemberId() <= 0
                || (requested.title() == null && requested.content() == null)) {
            throw contract("Node content update command payload fields are invalid");
        }
    }

    private void validateUpdatedNode(
            MeetingAnalysisCommandOutbox command,
            NodeContentUpdateRequestedCommand commandPayload,
            ProjectGraphSnapshot snapshot
    ) {
        ProjectGraphSnapshotNode updatedNode = snapshot.nodes().stream()
                .filter(node -> command.getTargetNodeId().equals(node.nodeId()))
                .findFirst()
                .orElseThrow(() -> contract(
                        "Node update snapshot does not contain the target node"
                ));
        NodeContentUpdateRequestedCommand.Payload requested = commandPayload.payload();
        if (updatedNode.nodeVersion() <= requested.expectedNodeVersion()) {
            throw contract("Updated node version did not advance");
        }
        if (requested.title() != null
                && !requested.title().equals(updatedNode.title())) {
            throw contract("Updated node title does not match the command");
        }
        if (requested.content() != null
                && !requested.content().equals(updatedNode.content())) {
            throw contract("Updated node content does not match the command");
        }
    }

    private AnalysisResultContractException contract(String message) {
        return new AnalysisResultContractException(message);
    }
}
