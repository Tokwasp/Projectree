package com.ssafy.projectree.domain.meeting.result.graph.command;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.NodeContentBatchUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.command.NodeContentUpdateRequestedCommand;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateItem;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateResponse;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateAcceptedResponse;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.operation.ProjectGraphOperationGuard;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectGraphSync;
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
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class GraphNodeUpdateService {

    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final ProjectNodeProjectionRepository nodeRepository;
    private final MeetingAnalysisCommandOutboxRepository outboxRepository;
    private final ObjectMapper objectMapper;
    private final Clock clock;
    private final ProjectGraphOperationGuard graphOperationGuard;

    @Transactional
    public NodeContentUpdateAcceptedResponse update(
            int projectId,
            String nodeId,
            int memberId,
            NodeContentUpdateRequest request
    ) {
        validateBasic(projectId, nodeId, memberId, request);
        String title = validateAndNormalizeTitle(request.title());
        String content = validateContent(request.content());

        projectRepository.findByIdForUpdate(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));
        if (!projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }
        ProjectNodeProjection node = nodeRepository.findByNodeIdAndProjectId(nodeId, projectId)
                .orElseThrow(() -> new CustomException(GraphQueryErrorCode.NODE_NOT_FOUND));
        if (node.getSourceNodeVersion() != request.expectedNodeVersion()) {
            throw new CustomException(GraphNodeUpdateErrorCode.NODE_VERSION_CONFLICT);
        }

        UUID commandId = UUID.randomUUID();
        Instant requestedAt = Instant.now(clock);
        graphOperationGuard.acquire(
                projectId,
                commandId,
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                requestedAt
        );
        NodeContentUpdateRequestedCommand command = new NodeContentUpdateRequestedCommand(
                NodeContentUpdateRequestedCommand.CURRENT_SCHEMA_VERSION,
                commandId,
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                requestedAt,
                projectId,
                new NodeContentUpdateRequestedCommand.Payload(
                        nodeId,
                        request.expectedNodeVersion(),
                        title,
                        content,
                        memberId
                )
        );
        String payload = serialize(command);
        MeetingAnalysisCommandOutbox savedOutbox = outboxRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pendingNodeContentUpdate(
                        commandId,
                        projectId,
                        nodeId,
                        command.commandType(),
                        payload,
                        memberId,
                        LocalDateTime.now(clock)
                )
        );
        log.info(
                "[AnalysisFlow] NODE_UPDATE_COMMAND_STAGED. commandId={}, commandType={}, outboxId={}, projectId={}, nodeId={}, requestedByMemberId={}, expectedNodeVersion={}, updateTitle={}, updateContent={}",
                commandId,
                command.commandType(),
                savedOutbox.getId(),
                projectId,
                nodeId,
                memberId,
                request.expectedNodeVersion(),
                title != null,
                content != null
        );
        return NodeContentUpdateAcceptedResponse.pending(
                commandId,
                nodeId,
                request.expectedNodeVersion()
        );
    }

    @Transactional
    public BatchNodeContentUpdateResponse updateBatch(
            int projectId,
            int memberId,
            BatchNodeContentUpdateRequest request
    ) {
        List<PreparedBatchItem> requestedItems = validateAndPrepareBatch(
                projectId, memberId, request
        );
        projectRepository.findByIdForUpdate(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));
        if (!projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }

        UUID commandId = UUID.randomUUID();
        Instant requestedAt = Instant.now(clock);
        ProjectGraphSync sync = graphOperationGuard.acquire(
                projectId,
                commandId,
                MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                requestedAt
        );

        Map<String, ProjectNodeProjection> currentNodesById = loadRequestedNodes(
                projectId, requestedItems
        );
        validateCurrentNodeVersions(requestedItems, currentNodesById);
        List<PreparedBatchItem> changedItems = requestedItems.stream()
                .filter(item -> !item.title().equals(
                        currentNodesById.get(item.nodeId()).getTitle()
                ))
                .toList();

        if (changedItems.isEmpty()) {
            graphOperationGuard.release(sync, commandId.toString(), "NO_CHANGE");
            return BatchNodeContentUpdateResponse.noChange(requestedItems.size());
        }

        NodeContentBatchUpdateRequestedCommand command =
                new NodeContentBatchUpdateRequestedCommand(
                        NodeContentBatchUpdateRequestedCommand.CURRENT_SCHEMA_VERSION,
                        commandId,
                        MeetingAnalysisCommandType.NODE_CONTENT_UPDATE_REQUESTED,
                        requestedAt,
                        projectId,
                        new NodeContentBatchUpdateRequestedCommand.Payload(
                                changedItems.stream()
                                        .map(item -> new NodeContentBatchUpdateRequestedCommand.NodeUpdate(
                                                item.nodeId(),
                                                item.expectedNodeVersion(),
                                                item.title()
                                        ))
                                        .toList(),
                                memberId
                        )
                );
        MeetingAnalysisCommandOutbox savedOutbox = outboxRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pendingNodeContentBatchUpdate(
                        commandId,
                        projectId,
                        command.commandType(),
                        serialize(command),
                        memberId,
                        LocalDateTime.now(clock)
                )
        );
        log.info(
                "[AnalysisFlow] NODE_BATCH_UPDATE_COMMAND_STAGED. commandId={}, commandType={}, outboxId={}, projectId={}, requestedByMemberId={}, requestedNodeCount={}, changedNodeCount={}",
                commandId,
                command.commandType(),
                savedOutbox.getId(),
                projectId,
                memberId,
                requestedItems.size(),
                changedItems.size()
        );
        return BatchNodeContentUpdateResponse.pending(
                commandId,
                requestedItems.size(),
                changedItems.size()
        );
    }

    private List<PreparedBatchItem> validateAndPrepareBatch(
            int projectId,
            int memberId,
            BatchNodeContentUpdateRequest request
    ) {
        if (projectId <= 0 || memberId <= 0 || request == null
                || request.nodes() == null || request.nodes().isEmpty()
                || request.nodes().size() > 100) {
            throw new CustomException(CommonErrorCode.INVALID_REQUEST);
        }

        Set<String> uniqueNodeIds = new LinkedHashSet<>();
        List<PreparedBatchItem> preparedItems = request.nodes().stream()
                .map(item -> prepareBatchItem(item, uniqueNodeIds))
                .toList();
        if (uniqueNodeIds.size() != preparedItems.size()) {
            throw new CustomException(
                    GraphNodeUpdateErrorCode.NODE_UPDATE_DUPLICATE_NODE_ID
            );
        }
        return preparedItems;
    }

    private PreparedBatchItem prepareBatchItem(
            BatchNodeContentUpdateItem item,
            Set<String> uniqueNodeIds
    ) {
        if (item == null || !isCanonicalNodeId(item.id())
                || item.title() == null
                || item.expectedNodeVersion() == null
                || item.expectedNodeVersion() <= 0) {
            throw new CustomException(CommonErrorCode.INVALID_REQUEST);
        }
        uniqueNodeIds.add(item.id());
        return new PreparedBatchItem(
                item.id(),
                validateAndNormalizeTitle(item.title()),
                item.expectedNodeVersion()
        );
    }

    private boolean isCanonicalNodeId(String nodeId) {
        if (nodeId == null || nodeId.isBlank()) {
            return false;
        }
        try {
            return UUID.fromString(nodeId).toString().equals(nodeId);
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private Map<String, ProjectNodeProjection> loadRequestedNodes(
            int projectId,
            List<PreparedBatchItem> requestedItems
    ) {
        List<String> requestedNodeIds = requestedItems.stream()
                .map(PreparedBatchItem::nodeId)
                .toList();
        Map<String, ProjectNodeProjection> nodesById = new LinkedHashMap<>();
        for (ProjectNodeProjection node : nodeRepository
                .findAllByProjectIdAndNodeIdIn(projectId, requestedNodeIds)) {
            if (nodesById.put(node.getNodeId(), node) != null) {
                throw new CustomException(GraphQueryErrorCode.GRAPH_PROJECTION_INCONSISTENT);
            }
        }
        return nodesById;
    }

    private void validateCurrentNodeVersions(
            List<PreparedBatchItem> requestedItems,
            Map<String, ProjectNodeProjection> currentNodesById
    ) {
        for (PreparedBatchItem requestedItem : requestedItems) {
            ProjectNodeProjection currentNode = currentNodesById.get(
                    requestedItem.nodeId()
            );
            if (currentNode == null || currentNode.getGraphState() != GraphNodeState.ACTIVE) {
                throw new CustomException(GraphQueryErrorCode.NODE_NOT_FOUND);
            }
            long currentNodeVersion = currentNode.getSourceNodeVersion();
            if (currentNodeVersion != requestedItem.expectedNodeVersion()) {
                throw new CustomException(GraphNodeUpdateErrorCode.NODE_VERSION_CONFLICT);
            }
        }
    }

    private void validateBasic(
            int projectId,
            String nodeId,
            int memberId,
            NodeContentUpdateRequest request
    ) {
        if (projectId <= 0 || memberId <= 0 || nodeId == null || nodeId.isBlank()
                || request == null || request.expectedNodeVersion() == null
                || request.expectedNodeVersion() <= 0) {
            throw new CustomException(CommonErrorCode.INVALID_REQUEST);
        }
        if (request.title() == null && request.content() == null) {
            throw new CustomException(GraphNodeUpdateErrorCode.NODE_UPDATE_EMPTY);
        }
    }

    private String validateAndNormalizeTitle(String title) {
        if (title == null) {
            return null;
        }
        String normalized = title.strip();
        if (normalized.isBlank() || normalized.length() > 255) {
            throw new CustomException(GraphNodeUpdateErrorCode.NODE_TITLE_INVALID);
        }
        return normalized;
    }

    private String validateContent(String content) {
        if (content != null && (content.isBlank() || content.length() > 65_535)) {
            throw new CustomException(GraphNodeUpdateErrorCode.NODE_CONTENT_INVALID);
        }
        return content;
    }

    private String serialize(NodeContentUpdateRequestedCommand command) {
        try {
            return objectMapper.writeValueAsString(command);
        } catch (JacksonException exception) {
            throw new CustomException(GraphNodeUpdateErrorCode.NODE_UPDATE_SERIALIZATION_FAILED);
        }
    }

    private String serialize(NodeContentBatchUpdateRequestedCommand command) {
        try {
            return objectMapper.writeValueAsString(command);
        } catch (JacksonException exception) {
            throw new CustomException(GraphNodeUpdateErrorCode.NODE_UPDATE_SERIALIZATION_FAILED);
        }
    }

    private record PreparedBatchItem(
            String nodeId,
            String title,
            long expectedNodeVersion
    ) {
    }
}
