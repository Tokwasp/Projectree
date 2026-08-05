package com.ssafy.projectree.domain.meeting.result.graph.query;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphTreeNodeResponse;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.Collection;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

@Slf4j
@Component
public class GraphTreeAssembler {

    private static final List<GraphNodeCategory> CATEGORY_ORDER = List.of(
            GraphNodeCategory.BACKEND,
            GraphNodeCategory.FRONTEND,
            GraphNodeCategory.DESIGN,
            GraphNodeCategory.INFRA,
            GraphNodeCategory.PLANNING,
            GraphNodeCategory.AI
    );

    private static final Comparator<ProjectNodeProjection> NODE_ORDER = Comparator
            .comparing(ProjectNodeProjection::getSourceCreatedAt)
            .thenComparing(ProjectNodeProjection::getNodeId);

    public GraphTreeNodeResponse assemble(
            int projectId,
            String projectTitle,
            long graphVersion,
            Collection<ProjectNodeProjection> activeNodes
    ) {
        Map<String, ProjectNodeProjection> nodesById = indexNodes(projectId, graphVersion, activeNodes);
        Map<String, List<ProjectNodeProjection>> childrenByParentId = new HashMap<>();
        Map<GraphNodeCategory, List<ProjectNodeProjection>> decisionsByCategory = new EnumMap<>(GraphNodeCategory.class);

        for (ProjectNodeProjection node : nodesById.values()) {
            validateAndIndex(node, nodesById, childrenByParentId, decisionsByCategory, projectId, graphVersion);
        }

        detectCycles(nodesById, childrenByParentId, projectId, graphVersion);
        Set<String> includedNodeIds = new HashSet<>();
        List<GraphTreeNodeResponse> categoryRoots = new ArrayList<>();
        for (GraphNodeCategory category : CATEGORY_ORDER) {
            List<GraphTreeNodeResponse> decisions = decisionsByCategory
                    .getOrDefault(category, List.of())
                    .stream()
                    .sorted(NODE_ORDER)
                    .map(node -> toGraphNode(
                            node, childrenByParentId, includedNodeIds, projectId, graphVersion
                    ))
                    .toList();
            categoryRoots.add(new GraphTreeNodeResponse(
                    "category:" + category.name(),
                    GraphTreeNodeKind.CATEGORY_ROOT,
                    category.name(),
                    category,
                    null,
                    null,
                    null,
                    null,
                    decisions
            ));
        }

        if (includedNodeIds.size() != nodesById.size()) {
            inconsistent(projectId, null, null, graphVersion, "ACTIVE_NODE_NOT_INCLUDED_EXACTLY_ONCE");
        }

        return new GraphTreeNodeResponse(
                "project:" + projectId,
                GraphTreeNodeKind.PROJECT_ROOT,
                projectTitle,
                null,
                null,
                null,
                null,
                null,
                categoryRoots
        );
    }

    private Map<String, ProjectNodeProjection> indexNodes(
            int projectId,
            long graphVersion,
            Collection<ProjectNodeProjection> nodes
    ) {
        Map<String, ProjectNodeProjection> nodesById = new HashMap<>();
        for (ProjectNodeProjection node : nodes) {
            if (node == null || node.getNodeId() == null || node.getNodeId().isBlank()) {
                inconsistent(projectId, null, null, graphVersion, "INVALID_NODE_ID");
            }
            if (nodesById.putIfAbsent(node.getNodeId(), node) != null) {
                inconsistent(projectId, node.getNodeId(), node.getParentNodeId(), graphVersion, "DUPLICATE_NODE_ID");
            }
        }
        return nodesById;
    }

    private void validateAndIndex(
            ProjectNodeProjection node,
            Map<String, ProjectNodeProjection> nodesById,
            Map<String, List<ProjectNodeProjection>> childrenByParentId,
            Map<GraphNodeCategory, List<ProjectNodeProjection>> decisionsByCategory,
            int projectId,
            long graphVersion
    ) {
        if (node.getNodeType() == null || node.getCategory() == null || node.getSourceCreatedAt() == null) {
            inconsistent(projectId, node.getNodeId(), node.getParentNodeId(), graphVersion, "MISSING_REQUIRED_NODE_FIELD");
        }

        if (node.getNodeType() == GraphNodeType.DECISION) {
            if (node.getParentNodeId() != null) {
                inconsistent(projectId, node.getNodeId(), node.getParentNodeId(), graphVersion, "DECISION_HAS_PARENT");
            }
            decisionsByCategory.computeIfAbsent(node.getCategory(), ignored -> new ArrayList<>()).add(node);
            return;
        }

        ProjectNodeProjection parent = nodesById.get(node.getParentNodeId());
        if (parent == null) {
            inconsistent(projectId, node.getNodeId(), node.getParentNodeId(), graphVersion, "PARENT_NOT_FOUND");
        }
        if (parent.getCategory() != node.getCategory()) {
            inconsistent(projectId, node.getNodeId(), node.getParentNodeId(), graphVersion, "PARENT_CATEGORY_MISMATCH");
        }
        if (node.getNodeType() == GraphNodeType.ACTION && parent.getNodeType() != GraphNodeType.DECISION) {
            inconsistent(projectId, node.getNodeId(), node.getParentNodeId(), graphVersion, "ACTION_PARENT_IS_NOT_DECISION");
        }
        if (node.getNodeType() == GraphNodeType.ISSUE
                && parent.getNodeType() != GraphNodeType.DECISION
                && parent.getNodeType() != GraphNodeType.ACTION) {
            inconsistent(projectId, node.getNodeId(), node.getParentNodeId(), graphVersion, "ISSUE_PARENT_TYPE_INVALID");
        }
        childrenByParentId.computeIfAbsent(node.getParentNodeId(), ignored -> new ArrayList<>()).add(node);
    }

    private void detectCycles(
            Map<String, ProjectNodeProjection> nodesById,
            Map<String, List<ProjectNodeProjection>> childrenByParentId,
            int projectId,
            long graphVersion
    ) {
        Map<String, VisitState> visitStates = new HashMap<>();
        for (String nodeId : nodesById.keySet()) {
            visit(nodeId, childrenByParentId, visitStates, projectId, graphVersion);
        }
    }

    private void visit(
            String nodeId,
            Map<String, List<ProjectNodeProjection>> childrenByParentId,
            Map<String, VisitState> visitStates,
            int projectId,
            long graphVersion
    ) {
        VisitState state = visitStates.get(nodeId);
        if (state == VisitState.VISITING) {
            inconsistent(projectId, nodeId, null, graphVersion, "CYCLE_DETECTED");
        }
        if (state == VisitState.VISITED) {
            return;
        }
        visitStates.put(nodeId, VisitState.VISITING);
        for (ProjectNodeProjection child : childrenByParentId.getOrDefault(nodeId, List.of())) {
            visit(child.getNodeId(), childrenByParentId, visitStates, projectId, graphVersion);
        }
        visitStates.put(nodeId, VisitState.VISITED);
    }

    private GraphTreeNodeResponse toGraphNode(
            ProjectNodeProjection node,
            Map<String, List<ProjectNodeProjection>> childrenByParentId,
            Set<String> includedNodeIds,
            int projectId,
            long graphVersion
    ) {
        if (!includedNodeIds.add(node.getNodeId())) {
            inconsistent(
                    projectId,
                    node.getNodeId(),
                    node.getParentNodeId(),
                    graphVersion,
                    "NODE_INCLUDED_MORE_THAN_ONCE"
            );
        }
        List<GraphTreeNodeResponse> children = childrenByParentId
                .getOrDefault(node.getNodeId(), List.of())
                .stream()
                .sorted(NODE_ORDER)
                .map(child -> toGraphNode(
                        child, childrenByParentId, includedNodeIds, projectId, graphVersion
                ))
                .toList();
        return new GraphTreeNodeResponse(
                node.getNodeId(),
                GraphTreeNodeKind.GRAPH_NODE,
                node.getTitle(),
                node.getCategory(),
                node.getNodeType(),
                node.getSourceMeetingId(),
                node.getSourceNodeVersion(),
                node.getSourceUpdatedAt(),
                children
        );
    }

    private void inconsistent(
            int projectId,
            String nodeId,
            String parentNodeId,
            long graphVersion,
            String reason
    ) {
        log.error(
                "Graph projection inconsistency. projectId={}, nodeId={}, parentNodeId={}, graphVersion={}, reason={}",
                projectId, nodeId, parentNodeId, graphVersion, reason
        );
        throw new com.ssafy.projectree.global.exception.CustomException(
                GraphQueryErrorCode.GRAPH_PROJECTION_INCONSISTENT
        );
    }

    private enum VisitState {
        VISITING,
        VISITED
    }
}
