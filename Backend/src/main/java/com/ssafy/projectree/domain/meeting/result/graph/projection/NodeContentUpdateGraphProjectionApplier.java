package com.ssafy.projectree.domain.meeting.result.graph.projection;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeContentBatchUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.event.AnalysisResultEventEnvelope;
import com.ssafy.projectree.domain.meeting.result.exception.AnalysisResultContractException;
import com.ssafy.projectree.domain.meeting.result.graph.event.GraphResultSourceType;
import com.ssafy.projectree.domain.meeting.result.graph.event.ProjectGraphChangedPayload;
import com.ssafy.projectree.domain.meeting.result.graph.command.NodeContentUpdateCommandPayloadParser;
import com.ssafy.projectree.domain.meeting.result.graph.command.NodeContentUpdateCommandPayloadParser.ParsedCommand;
import com.ssafy.projectree.domain.meeting.result.graph.command.NodeContentUpdateCommandPayloadParser.RequestedNodeUpdate;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
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
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;
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
    private final ProjectGraphOperationGuard graphOperationGuard;

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
        ParsedCommand commandPayload = new NodeContentUpdateCommandPayloadParser(objectMapper)
                .parse(event, command);

        ProjectGraphSync sync = graphSyncRepository.findByProjectIdForUpdate(event.projectId())
                .orElseThrow(() -> new IllegalStateException(
                        "Project graph sync does not exist"
                ));
        resultInboxService.registerProcessed(event);

        boolean projectionUpdated;
        boolean alreadyApplied;
        if (commandPayload.schemaVersion()
                == NodeContentBatchUpdateRequestedCommand.CURRENT_SCHEMA_VERSION) {
            alreadyApplied = isV2AlreadyApplied(event, payload, sync);
            if (alreadyApplied) {
                projectionUpdated = false;
            } else {
                validateFreshV2Result(event, payload, sync);
                projectionUpdated = true;
            }
        } else {
            projectionUpdated = payload.graphVersion() > sync.getCurrentGraphVersion();
            alreadyApplied = !projectionUpdated
                    && !sync.hasActiveCommand()
                    && event.commandId().equals(sync.getLastCommandId());
        }
        if (projectionUpdated) {
            validateUpdatedNodes(commandPayload, snapshot);
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
        boolean released = graphOperationGuard.release(
                sync,
                event.commandId(),
                "GRAPH_PROJECTION_APPLIED"
        );
        if (!released && !alreadyApplied) {
            throw contract(
                    "Node content update result does not own the active graph operation"
            );
        }
        return new GraphProjectionApplyResult(
                null,
                projectionUpdated,
                payload.graphVersion(),
                sync.getCurrentGraphVersion()
        );
    }

    private void validateFreshV2Result(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            ProjectGraphSync sync
    ) {
        if (!sync.hasActiveCommand()
                || !event.commandId().equals(sync.getActiveCommandId())
                || sync.getActiveCommandType()
                != MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED) {
            throw contract(
                    "Node content update V2 result does not own the active graph operation"
            );
        }

        long expectedGraphVersion;
        try {
            expectedGraphVersion = Math.addExact(sync.getCurrentGraphVersion(), 1L);
        } catch (ArithmeticException exception) {
            throw contract("Node content update graph version cannot advance");
        }
        if (payload.graphVersion() != expectedGraphVersion) {
            throw contract(
                    "Node content update V2 result graphVersion must advance exactly once"
            );
        }
    }

    private boolean isV2AlreadyApplied(
            AnalysisResultEventEnvelope event,
            ProjectGraphChangedPayload payload,
            ProjectGraphSync sync
    ) {
        return !sync.hasActiveCommand()
                && event.commandId().equals(sync.getLastCommandId())
                && payload.graphVersion() == sync.getCurrentGraphVersion();
    }

    private void validateUpdatedNodes(
            ParsedCommand commandPayload,
            ProjectGraphSnapshot snapshot
    ) {
        Map<String, ProjectGraphSnapshotNode> snapshotNodesById = new HashMap<>();
        for (ProjectGraphSnapshotNode snapshotNode : snapshot.nodes()) {
            snapshotNodesById.put(snapshotNode.nodeId(), snapshotNode);
        }
        for (RequestedNodeUpdate requestedNode : commandPayload.requestedNodes()) {
            ProjectGraphSnapshotNode updatedNode = snapshotNodesById.get(
                    requestedNode.nodeId()
            );
            if (updatedNode == null) {
                throw contract("Node update snapshot does not contain a requested node");
            }
            validateUpdatedNode(commandPayload.schemaVersion(), requestedNode, updatedNode);
        }
    }

    private void validateUpdatedNode(
            int schemaVersion,
            RequestedNodeUpdate requestedNode,
            ProjectGraphSnapshotNode updatedNode
    ) {
        boolean invalidVersion = schemaVersion == 1
                ? updatedNode.nodeVersion() <= requestedNode.expectedNodeVersion()
                : updatedNode.nodeVersion() != requestedNode.expectedNodeVersion() + 1;
        if (invalidVersion) {
            throw contract("Updated node version does not match the command");
        }
        if (requestedNode.title() != null
                && !requestedNode.title().equals(updatedNode.title())) {
            throw contract("Updated node title does not match the command");
        }
        if (requestedNode.content() != null
                && !requestedNode.content().equals(updatedNode.content())) {
            throw contract("Updated node content does not match the command");
        }
    }

    private AnalysisResultContractException contract(String message) {
        return new AnalysisResultContractException(message);
    }
}
