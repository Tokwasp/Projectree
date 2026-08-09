package com.ssafy.projectree.domain.meeting.result.graph.query;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.meeting.result.graph.delete.repository.NodeDeleteCommandItemRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.NodeEvidenceProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.NodeEvidenceProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectGraphSyncRepository;
import com.ssafy.projectree.domain.meeting.result.graph.projection.repository.ProjectNodeProjectionRepository;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphEvidenceResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphMergedSourcesResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodeDetailItemResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodeDetailResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodePageResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodeSummaryResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphTreeResponse;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

@Service
@Slf4j
@RequiredArgsConstructor
@Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
public class GraphQueryService {

    private static final Sort UNATTACHED_SORT = Sort.by(
            Sort.Order.desc("sourceUpdatedAt"),
            Sort.Order.asc("nodeId")
    );
    private static final Sort MEETING_NODE_SORT = Sort.by(
            Sort.Order.asc("sourceCreatedAt"),
            Sort.Order.asc("nodeId")
    );
    private static final Comparator<NodeEvidenceProjection> EVIDENCE_ORDER = Comparator
            .comparingInt(NodeEvidenceProjection::getEvidenceOrder)
            .thenComparing(NodeEvidenceProjection::getEvidenceId);
    private static final Comparator<ProjectNodeProjection> NODE_CREATED_ORDER = Comparator
            .comparing(ProjectNodeProjection::getSourceCreatedAt)
            .thenComparing(ProjectNodeProjection::getNodeId);
    private static final Comparator<ProjectNodeProjection> UNATTACHED_ORDER = Comparator
            .comparing(ProjectNodeProjection::getSourceUpdatedAt)
            .reversed()
            .thenComparing(ProjectNodeProjection::getNodeId);

    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final MeetingRepository meetingRepository;
    private final ProjectGraphSyncRepository graphSyncRepository;
    private final ProjectNodeProjectionRepository nodeRepository;
    private final NodeEvidenceProjectionRepository evidenceRepository;
    private final NodeDeleteCommandItemRepository nodeDeleteCommandItemRepository;
    private final GraphTreeAssembler graphTreeAssembler;

    public GraphTreeResponse getTree(int projectId, int memberId) {
        Project project = requireAccessibleProject(projectId, memberId);
        GraphMetadata metadata = graphMetadata(projectId);
        List<ProjectNodeProjection> activeNodes = metadata.hasProjection()
                ? nodeRepository.findAllByProjectIdAndGraphState(projectId, GraphNodeState.ACTIVE)
                : List.of();
        Set<String> hiddenNodeIds = metadata.hasProjection()
                ? findPendingDeleteNodeIds(projectId)
                : Set.of();
        List<ProjectNodeProjection> visibleNodes = activeNodes.stream()
                .filter(node -> !hiddenNodeIds.contains(node.getNodeId()))
                .toList();
        return new GraphTreeResponse(
                projectId,
                metadata.graphVersion(),
                metadata.graphSyncedAt(),
                graphTreeAssembler.assemble(
                        projectId,
                        project.getTitle(),
                        metadata.graphVersion(),
                        visibleNodes
                )
        );
    }

    public GraphNodePageResponse getUnattachedNodes(
            int projectId,
            int memberId,
            String graphState,
            int page,
            int size
    ) {
        requireAccessibleProject(projectId, memberId);
        validateUnattachedGraphState(graphState);
        GraphMetadata metadata = graphMetadata(projectId);
        Page<ProjectNodeProjection> nodes = metadata.hasProjection()
                ? visiblePage(
                        nodeRepository.findAllByProjectIdAndGraphState(
                                projectId,
                                GraphNodeState.UNATTACHED
                        ),
                        findPendingDeleteNodeIds(projectId),
                        page,
                        size,
                        UNATTACHED_ORDER
                )
                : Page.empty(PageRequest.of(page, size, UNATTACHED_SORT));
        return pageResponse(projectId, metadata, nodes);
    }

    public GraphNodeDetailResponse getNodeDetail(int projectId, String nodeId, int memberId) {
        requireAccessibleProject(projectId, memberId);
        GraphMetadata metadata = graphMetadata(projectId);
        if (nodeDeleteCommandItemRepository
                .existsPendingNodeByProjectIdAndNodeId(projectId, nodeId)) {
            throw new CustomException(GraphQueryErrorCode.NODE_NOT_FOUND);
        }
        ProjectNodeProjection node = findNode(projectId, nodeId, metadata);
        List<GraphEvidenceResponse> evidences = evidenceRepository
                .findAllByNodeIdOrderByEvidenceOrderAscEvidenceIdAsc(nodeId)
                .stream()
                .map(this::toEvidenceResponse)
                .toList();
        return new GraphNodeDetailResponse(
                projectId,
                metadata.graphVersion(),
                metadata.graphSyncedAt(),
                toDetailResponse(node, evidences)
        );
    }

    public GraphMergedSourcesResponse getMergedSources(int projectId, String targetNodeId, int memberId) {
        requireAccessibleProject(projectId, memberId);
        GraphMetadata metadata = graphMetadata(projectId);
        Set<String> hiddenNodeIds = findPendingDeleteNodeIds(projectId);
        if (hiddenNodeIds.contains(targetNodeId)) {
            throw new CustomException(GraphQueryErrorCode.NODE_NOT_FOUND);
        }
        ProjectNodeProjection target = findNode(projectId, targetNodeId, metadata);
        if (target.getGraphState() != GraphNodeState.ACTIVE) {
            throw new CustomException(GraphQueryErrorCode.INVALID_MERGED_SOURCE_TARGET);
        }
        List<ProjectNodeProjection> sources = nodeRepository
                .findAllByProjectIdAndGraphStateAndMergedIntoNodeId(
                        projectId,
                        GraphNodeState.MERGED,
                        targetNodeId
                )
                .stream()
                .filter(source -> !hiddenNodeIds.contains(source.getNodeId()))
                .sorted(NODE_CREATED_ORDER)
                .toList();
        Map<String, List<GraphEvidenceResponse>> evidencesByNodeId = evidenceResponsesByNodeId(
                sources.stream().map(ProjectNodeProjection::getNodeId).collect(Collectors.toSet())
        );
        List<GraphNodeDetailItemResponse> items = sources.stream()
                .map(source -> toDetailResponse(source, evidencesByNodeId.getOrDefault(source.getNodeId(), List.of())))
                .toList();
        return new GraphMergedSourcesResponse(
                projectId,
                metadata.graphVersion(),
                metadata.graphSyncedAt(),
                targetNodeId,
                items
        );
    }

    public GraphNodePageResponse getMeetingNodes(
            int projectId,
            int meetingId,
            int memberId,
            int page,
            int size
    ) {
        requireAccessibleProject(projectId, memberId);
        Meeting meeting = meetingRepository.findByIdWithProject(meetingId)
                .orElseThrow(() -> new CustomException(MeetingErrorCode.MEETING_NOT_FOUND));
        if (meeting.getProject().getId() != projectId) {
            throw new CustomException(MeetingErrorCode.MEETING_PROJECT_MISMATCH);
        }
        GraphMetadata metadata = graphMetadata(projectId);
        Page<ProjectNodeProjection> nodes = metadata.hasProjection()
                ? visiblePage(
                        nodeRepository.findAllByProjectIdAndSourceMeetingId(
                                projectId,
                                meetingId
                        ),
                        findPendingDeleteNodeIds(projectId),
                        page,
                        size,
                        NODE_CREATED_ORDER
                )
                : Page.empty(PageRequest.of(page, size, MEETING_NODE_SORT));
        return pageResponse(projectId, metadata, nodes);
    }

    private Project requireAccessibleProject(int projectId, int memberId) {
        Project project = projectRepository.findById(projectId)
                .orElseThrow(() -> new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND));
        if (!projectMemberRepository.existsByProjectIdAndMemberId(projectId, memberId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
        }
        return project;
    }

    private GraphMetadata graphMetadata(int projectId) {
        return graphSyncRepository.findById(projectId)
                .map(sync -> {
                    if (sync.getCurrentGraphVersion() == 0 && nodeRepository.existsByProjectId(projectId)) {
                        throwProjectionInconsistency(projectId, 0, "SYNC_VERSION_ZERO_WITH_NODES");
                    }
                    return new GraphMetadata(
                            sync.getCurrentGraphVersion(),
                            sync.getSyncedAt(),
                            true
                    );
                })
                .orElseGet(() -> {
                    if (nodeRepository.existsByProjectId(projectId)) {
                        throwProjectionInconsistency(projectId, 0, "SYNC_MISSING_WITH_NODES");
                    }
                    return new GraphMetadata(0, null, false);
                });
    }

    private void throwProjectionInconsistency(int projectId, long graphVersion, String reason) {
        log.error(
                "Graph projection inconsistency. projectId={}, nodeId={}, parentNodeId={}, graphVersion={}, reason={}",
                projectId, null, null, graphVersion, reason
        );
        throw new CustomException(GraphQueryErrorCode.GRAPH_PROJECTION_INCONSISTENT);
    }

    private ProjectNodeProjection findNode(int projectId, String nodeId, GraphMetadata metadata) {
        if (!metadata.hasProjection()) {
            throw new CustomException(GraphQueryErrorCode.NODE_NOT_FOUND);
        }
        return nodeRepository.findByNodeIdAndProjectId(nodeId, projectId)
                .orElseThrow(() -> new CustomException(GraphQueryErrorCode.NODE_NOT_FOUND));
    }

    private void validateUnattachedGraphState(String graphState) {
        if (!GraphNodeState.UNATTACHED.name().equals(graphState)) {
            throw new CustomException(GraphQueryErrorCode.INVALID_GRAPH_STATE_QUERY);
        }
    }

    private GraphNodePageResponse pageResponse(
            int projectId,
            GraphMetadata metadata,
            Page<ProjectNodeProjection> nodes
    ) {
        return new GraphNodePageResponse(
                projectId,
                metadata.graphVersion(),
                metadata.graphSyncedAt(),
                nodes.getContent().stream().map(this::toSummaryResponse).toList(),
                nodes.getNumber(),
                nodes.getSize(),
                nodes.getTotalElements(),
                nodes.getTotalPages()
        );
    }

    private Set<String> findPendingDeleteNodeIds(int projectId) {
        return Set.copyOf(
                nodeDeleteCommandItemRepository.findPendingNodeIdsByProjectId(projectId)
        );
    }

    private Page<ProjectNodeProjection> visiblePage(
            List<ProjectNodeProjection> nodes,
            Set<String> hiddenNodeIds,
            int page,
            int size,
            Comparator<ProjectNodeProjection> order
    ) {
        List<ProjectNodeProjection> visibleNodes = nodes.stream()
                .filter(node -> !hiddenNodeIds.contains(node.getNodeId()))
                .sorted(order)
                .toList();
        Pageable pageable = PageRequest.of(page, size);
        long offset = pageable.getOffset();
        int fromIndex = (int) Math.min(offset, (long) visibleNodes.size());
        int toIndex = Math.min(fromIndex + pageable.getPageSize(), visibleNodes.size());
        return new PageImpl<>(
                visibleNodes.subList(fromIndex, toIndex),
                pageable,
                visibleNodes.size()
        );
    }

    private Map<String, List<GraphEvidenceResponse>> evidenceResponsesByNodeId(Set<String> nodeIds) {
        if (nodeIds.isEmpty()) {
            return Map.of();
        }
        return evidenceRepository.findAllByNodeIdIn(nodeIds).stream()
                .sorted(EVIDENCE_ORDER)
                .collect(Collectors.groupingBy(
                        NodeEvidenceProjection::getNodeId,
                        Collectors.mapping(this::toEvidenceResponse, Collectors.toList())
                ));
    }

    private GraphNodeSummaryResponse toSummaryResponse(ProjectNodeProjection node) {
        return new GraphNodeSummaryResponse(
                node.getNodeId(),
                node.getSourceMeetingId(),
                node.getParentNodeId(),
                node.getMergedIntoNodeId(),
                node.getNodeType(),
                node.getCategory(),
                node.getGraphState(),
                node.getTitle(),
                node.getLinkSource(),
                node.getSourceNodeVersion(),
                node.getSourceCreatedAt(),
                node.getSourceUpdatedAt()
        );
    }

    private GraphNodeDetailItemResponse toDetailResponse(
            ProjectNodeProjection node,
            List<GraphEvidenceResponse> evidences
    ) {
        return new GraphNodeDetailItemResponse(
                node.getNodeId(),
                node.getSourceMeetingId(),
                node.getParentNodeId(),
                node.getMergedIntoNodeId(),
                node.getNodeType(),
                node.getCategory(),
                node.getGraphState(),
                node.getTitle(),
                node.getContent(),
                node.getLinkSource(),
                node.getSourceNodeVersion(),
                node.getSourceCreatedAt(),
                node.getSourceUpdatedAt(),
                evidences
        );
    }

    private GraphEvidenceResponse toEvidenceResponse(NodeEvidenceProjection evidence) {
        return new GraphEvidenceResponse(
                evidence.getEvidenceId(),
                evidence.getMeetingId(),
                evidence.getQuoteText(),
                evidence.getSpeakerLabel(),
                evidence.getStartMs(),
                evidence.getEndMs(),
                evidence.getEvidenceOrder()
        );
    }

    private record GraphMetadata(long graphVersion, Instant graphSyncedAt, boolean hasProjection) {
    }
}
