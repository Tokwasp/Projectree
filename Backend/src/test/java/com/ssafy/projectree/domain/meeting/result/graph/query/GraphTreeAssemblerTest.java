package com.ssafy.projectree.domain.meeting.result.graph.query;

import com.ssafy.projectree.domain.meeting.result.graph.projection.entity.ProjectNodeProjection;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphTreeNodeResponse;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphLinkSource;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.ProjectGraphSnapshotNode;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class GraphTreeAssemblerTest {

    private final GraphTreeAssembler assembler = new GraphTreeAssembler();

    @Test
    void createsEveryCategoryRootInFixedOrder() {
        ProjectNodeProjection decision = node("10000000-0000-0000-0000-000000000000", 1, null,
                GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 2);

        GraphTreeNodeResponse root = assembler.assemble(1, "Projectree", 7, List.of(decision));

        assertThat(root.id()).isEqualTo("project:1");
        assertThat(root.title()).isEqualTo("Projectree");
        assertThat(root.children()).hasSize(6);
        assertThat(root.children()).extracting(GraphTreeNodeResponse::id).containsExactly(
                "category:BACKEND", "category:FRONTEND", "category:DESIGN", "category:INFRA",
                "category:PLANNING", "category:AI"
        );
        assertThat(root.children().getFirst().children()).extracting(GraphTreeNodeResponse::id)
                .containsExactly(decision.getNodeId());
        assertThat(root.children().get(1).children()).isEmpty();
    }

    @Test
    void assemblesDecisionActionAndIssueOnceWithStableSort() {
        String decisionId = "10000000-0000-0000-0000-000000000000";
        String laterDecisionId = "20000000-0000-0000-0000-000000000000";
        ProjectNodeProjection decision = node(decisionId, 1, null,
                GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 2);
        ProjectNodeProjection action = node("30000000-0000-0000-0000-000000000000", 1, decisionId,
                GraphNodeType.ACTION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 3);
        ProjectNodeProjection issue = node("40000000-0000-0000-0000-000000000000", 1, action.getNodeId(),
                GraphNodeType.ISSUE, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 4);
        ProjectNodeProjection laterDecision = node(laterDecisionId, 1, null,
                GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 5);

        GraphTreeNodeResponse backend = assembler
                .assemble(1, "Projectree", 7, List.of(laterDecision, issue, action, decision))
                .children()
                .getFirst();

        assertThat(backend.children()).extracting(GraphTreeNodeResponse::id)
                .containsExactly(decisionId, laterDecisionId);
        assertThat(backend.children().getFirst().children()).extracting(GraphTreeNodeResponse::id)
                .containsExactly(action.getNodeId());
        assertThat(backend.children().getFirst().children().getFirst().children())
                .extracting(GraphTreeNodeResponse::id)
                .containsExactly(issue.getNodeId());
    }

    @Test
    void rejectsMissingParentAndCategoryMismatchAsProjectionInconsistency() {
        ProjectNodeProjection missingParent = node("10000000-0000-0000-0000-000000000000", 1,
                "missing", GraphNodeType.ACTION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1);
        ProjectNodeProjection decision = node("20000000-0000-0000-0000-000000000000", 1, null,
                GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1);
        ProjectNodeProjection wrongCategory = node("30000000-0000-0000-0000-000000000000", 1,
                decision.getNodeId(), GraphNodeType.ACTION, GraphNodeCategory.FRONTEND,
                GraphNodeState.ACTIVE, 2);

        assertInconsistent(List.of(missingParent));
        assertInconsistent(List.of(decision, wrongCategory));
    }

    @Test
    void rejectsDecisionWithParentAndInvalidParentType() {
        ProjectNodeProjection decision = node("10000000-0000-0000-0000-000000000000", 1, null,
                GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1);
        ProjectNodeProjection action = node("20000000-0000-0000-0000-000000000000", 1,
                decision.getNodeId(), GraphNodeType.ACTION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 2);
        ProjectNodeProjection invalidDecision = node("30000000-0000-0000-0000-000000000000", 1,
                decision.getNodeId(), GraphNodeType.DECISION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 3);
        ProjectNodeProjection invalidAction = node("40000000-0000-0000-0000-000000000000", 1,
                action.getNodeId(), GraphNodeType.ACTION, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 4);

        assertInconsistent(List.of(decision, invalidDecision));
        assertInconsistent(List.of(decision, action, invalidAction));
    }

    @Test
    void rejectsRootUnreachableThreeNodeCycleAsProjectionInconsistency() {
        ProjectNodeProjection first = node("10000000-0000-0000-0000-000000000000", 1,
                "20000000-0000-0000-0000-000000000000", GraphNodeType.ISSUE,
                GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 1);
        ProjectNodeProjection second = node("20000000-0000-0000-0000-000000000000", 1,
                "30000000-0000-0000-0000-000000000000", GraphNodeType.ISSUE,
                GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 2);
        ProjectNodeProjection third = node("30000000-0000-0000-0000-000000000000", 1,
                first.getNodeId(), GraphNodeType.ISSUE, GraphNodeCategory.BACKEND, GraphNodeState.ACTIVE, 3);

        assertInconsistent(List.of(first, second, third));
    }

    private void assertInconsistent(List<ProjectNodeProjection> nodes) {
        assertThatThrownBy(() -> assembler.assemble(1, "Projectree", 7, nodes))
                .isInstanceOf(CustomException.class)
                .extracting(error -> ((CustomException) error).getErrorCode())
                .isEqualTo(GraphQueryErrorCode.GRAPH_PROJECTION_INCONSISTENT);
    }

    private ProjectNodeProjection node(
            String nodeId,
            int projectId,
            String parentNodeId,
            GraphNodeType type,
            GraphNodeCategory category,
            GraphNodeState state,
            long second
    ) {
        Instant timestamp = Instant.parse("2026-08-05T00:00:0" + second + "Z");
        return ProjectNodeProjection.from(projectId, new ProjectGraphSnapshotNode(
                nodeId, 1, parentNodeId, null, type, category, state,
                nodeId, "content", GraphLinkSource.AI, 1, timestamp, timestamp
        ), timestamp);
    }
}
