package com.ssafy.projectree.domain.meeting.result.graph.delete;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeDeleteCommandPayload;
import com.ssafy.projectree.domain.meeting.command.NodeDeleteRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteAcceptedResponse;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteRequest;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommand;
import com.ssafy.projectree.domain.meeting.result.graph.delete.entity.NodeDeleteCommandItem;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandRepository;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.query.GraphQueryErrorCode;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDateTime;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class GraphNodeDeleteService {

    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final ProjectNodeProjectionRepository nodeRepository;
    private final NodeDeleteCommandRepository commandRepository;
    private final NodeDeleteCommandItemRepository itemRepository;
    private final MeetingAnalysisCommandOutboxRepository outboxRepository;
    private final ProjectGraphOperationGuard graphOperationGuard;
    private final ObjectMapper objectMapper;
    private final Clock clock;

    @Transactional
    public GraphNodeDeleteAcceptedResponse deleteNodes(
            int projectId,
            int memberId,
            GraphNodeDeleteRequest request
    ) {
        validateBasic(projectId, memberId, request);
        validateProjectAccess(projectId, memberId);

        LinkedHashSet<String> requestedIds = new LinkedHashSet<>(request.nodeIds());
        if (requestedIds.size() != request.nodeIds().size()) {
            throw new CustomException(
                    GraphNodeDeleteErrorCode.NODE_DELETE_DUPLICATE_NODE_ID
            );
        }

        UUID commandId = UUID.randomUUID();
        Instant requestedAt = Instant.now(clock);
        LocalDateTime requestedAtLocal =
                LocalDateTime.ofInstant(requestedAt, clock.getZone());
        ProjectGraphSync sync = graphOperationGuard.acquire(
                projectId,
                commandId,
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                requestedAt
        );
        if (sync.getCurrentGraphVersion() != request.expectedGraphVersion()) {
            throw new CustomException(
                    GraphNodeDeleteErrorCode.GRAPH_VERSION_CONFLICT
            );
        }

        Map<String, ProjectNodeProjection> nodesById =
                loadProjectNodes(projectId);
        validateRequestedNodes(requestedIds, nodesById);
        validateActiveChildClosure(requestedIds, nodesById.values());
        LinkedHashSet<String> effectiveIds =
                expandReverseMergeClosure(requestedIds, nodesById.values());
        List<String> mergedSourceIds = effectiveIds.stream()
                .filter(nodeId -> !requestedIds.contains(nodeId))
                .toList();

        NodeDeleteCommand deleteCommand = commandRepository.saveAndFlush(
                NodeDeleteCommand.pending(
                        commandId,
                        projectId,
                        request.expectedGraphVersion(),
                        memberId,
                        requestedIds.size(),
                        mergedSourceIds.size(),
                        requestedAtLocal
                )
        );
        itemRepository.saveAll(createItems(
                deleteCommand,
                requestedIds,
                mergedSourceIds,
                nodesById,
                requestedAtLocal
        ));

        NodeDeleteRequestedCommand sqsCommand = new NodeDeleteRequestedCommand(
                NodeDeleteRequestedCommand.CURRENT_SCHEMA_VERSION,
                commandId,
                MeetingAnalysisCommandType.NODE_DELETE_REQUESTED,
                requestedAt,
                projectId,
                new NodeDeleteCommandPayload(
                        List.copyOf(requestedIds),
                        request.expectedGraphVersion(),
                        memberId
                )
        );
        MeetingAnalysisCommandOutbox outbox = outboxRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pendingNodeDelete(
                        commandId,
                        projectId,
                        serialize(sqsCommand),
                        memberId,
                        requestedAtLocal
                )
        );
        deleteCommand.attachOutbox(outbox.getId());
        commandRepository.saveAndFlush(deleteCommand);

        log.info(
                "[AnalysisFlow] NODE_DELETE_COMMAND_STAGED. projectId={}, commandId={}, requestedNodeCount={}, mergedSourceCount={}, totalNodeCount={}, expectedGraphVersion={}",
                projectId,
                commandId,
                requestedIds.size(),
                mergedSourceIds.size(),
                effectiveIds.size(),
                request.expectedGraphVersion()
        );
        return GraphNodeDeleteAcceptedResponse.pending(
                commandId,
                projectId,
                List.copyOf(requestedIds),
                request.expectedGraphVersion()
        );
    }

    private void validateBasic(
            int projectId,
            int memberId,
            GraphNodeDeleteRequest request
    ) {
        if (projectId <= 0 || memberId <= 0 || request == null
                || request.nodeIds() == null || request.nodeIds().isEmpty()
                || request.expectedGraphVersion() < 0) {
            throw new CustomException(CommonErrorCode.INVALID_REQUEST);
        }
    }

    private void validateProjectAccess(int projectId, int memberId) {
        if (!projectRepository.existsById(projectId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND);
        }
        if (!projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }
    }

    private Map<String, ProjectNodeProjection> loadProjectNodes(int projectId) {
        Map<String, ProjectNodeProjection> nodesById = new LinkedHashMap<>();
        for (ProjectNodeProjection node : nodeRepository.findAllByProjectId(projectId)) {
            if (nodesById.put(node.getNodeId(), node) != null) {
                throw new CustomException(
                        GraphQueryErrorCode.GRAPH_PROJECTION_INCONSISTENT
                );
            }
        }
        return nodesById;
    }

    private void validateRequestedNodes(
            Set<String> requestedIds,
            Map<String, ProjectNodeProjection> nodesById
    ) {
        for (String requestedId : requestedIds) {
            ProjectNodeProjection node = nodesById.get(requestedId);
            if (node == null || node.getGraphState() != GraphNodeState.ACTIVE) {
                throw new CustomException(GraphQueryErrorCode.NODE_NOT_FOUND);
            }
        }
    }

    private void validateActiveChildClosure(
            Set<String> requestedIds,
            Iterable<ProjectNodeProjection> projectNodes
    ) {
        for (ProjectNodeProjection node : projectNodes) {
            if (node.getGraphState() == GraphNodeState.ACTIVE
                    && requestedIds.contains(node.getParentNodeId())
                    && !requestedIds.contains(node.getNodeId())) {
                throw new CustomException(
                        GraphNodeDeleteErrorCode.NODE_DELETE_SET_INCOMPLETE
                );
            }
        }
    }

    private LinkedHashSet<String> expandReverseMergeClosure(
            Set<String> requestedIds,
            Iterable<ProjectNodeProjection> projectNodes
    ) {
        Map<String, List<String>> sourcesByTarget = new LinkedHashMap<>();
        for (ProjectNodeProjection node : projectNodes) {
            if (node.getMergedIntoNodeId() != null) {
                sourcesByTarget.computeIfAbsent(
                        node.getMergedIntoNodeId(),
                        ignored -> new ArrayList<>()
                ).add(node.getNodeId());
            }
        }

        LinkedHashSet<String> effectiveIds = new LinkedHashSet<>(requestedIds);
        Deque<String> queue = new ArrayDeque<>(requestedIds);
        while (!queue.isEmpty()) {
            String targetId = queue.removeFirst();
            for (String sourceId : sourcesByTarget.getOrDefault(targetId, List.of())) {
                if (effectiveIds.add(sourceId)) {
                    queue.addLast(sourceId);
                }
            }
        }
        return effectiveIds;
    }

    private List<NodeDeleteCommandItem> createItems(
            NodeDeleteCommand command,
            Set<String> requestedIds,
            List<String> mergedSourceIds,
            Map<String, ProjectNodeProjection> nodesById,
            LocalDateTime createdAt
    ) {
        List<NodeDeleteCommandItem> items =
                new ArrayList<>(requestedIds.size() + mergedSourceIds.size());
        for (String nodeId : requestedIds) {
            items.add(NodeDeleteCommandItem.requested(
                    command,
                    nodeId,
                    requireNode(nodesById, nodeId).getSourceNodeVersion(),
                    createdAt
            ));
        }
        for (String nodeId : mergedSourceIds) {
            items.add(NodeDeleteCommandItem.mergedSource(
                    command,
                    nodeId,
                    requireNode(nodesById, nodeId).getSourceNodeVersion(),
                    createdAt
            ));
        }
        return items;
    }

    private ProjectNodeProjection requireNode(
            Map<String, ProjectNodeProjection> nodesById,
            String nodeId
    ) {
        ProjectNodeProjection node = nodesById.get(nodeId);
        if (node == null) {
            throw new CustomException(
                    GraphQueryErrorCode.GRAPH_PROJECTION_INCONSISTENT
            );
        }
        return node;
    }

    private String serialize(NodeDeleteRequestedCommand command) {
        try {
            return objectMapper.writeValueAsString(command);
        } catch (JacksonException exception) {
            throw new CustomException(
                    GraphNodeDeleteErrorCode.NODE_DELETE_SERIALIZATION_FAILED
            );
        }
    }
}
