package com.ssafy.projectree.domain.meeting.result.graph.query;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphMergedSourcesResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodeDetailItemResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodeDetailResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodePageResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphNodeSummaryResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphTreeNodeResponse;
import com.ssafy.projectree.domain.meeting.result.graph.query.dto.GraphTreeResponse;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeCategory;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeState;
import com.ssafy.projectree.domain.meeting.result.graph.snapshot.GraphNodeType;
import com.ssafy.projectree.global.config.session.SessionConst;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;

import java.time.Instant;
import java.util.List;

import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GraphQueryControllerTest extends ControllerTestSupport {

    private static final int PROJECT_ID = 11;
    private static final int MEMBER_ID = 22;
    private static final String NODE_ID = "11111111-1111-1111-1111-111111111111";

    @Test
    void servesTreeThroughExistingApiPrefixAndSessionPrincipal() throws Exception {
        when(graphQueryService.getTree(PROJECT_ID, MEMBER_ID)).thenReturn(tree());

        mockMvc.perform(get("/api/projects/{projectId}/nodes/tree", PROJECT_ID).session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.data.projectId").value(PROJECT_ID))
                .andExpect(jsonPath("$.data.graphVersion").value(5))
                .andExpect(jsonPath("$.data.root.id").value("project:11"))
                .andExpect(jsonPath("$.data.root.children.length()").value(7))
                .andExpect(jsonPath("$.data.root.children[0].children[0].kind")
                        .value("GRAPH_NODE"))
                .andExpect(jsonPath("$.data.root.children[0].children[0].nodeVersion")
                        .value(3));

        verify(graphQueryService).getTree(PROJECT_ID, MEMBER_ID);
    }

    @Test
    void servesUnattachedPageWithDefaultPagination() throws Exception {
        when(graphQueryService.getUnattachedNodes(PROJECT_ID, MEMBER_ID, "UNATTACHED", 0, 20))
                .thenReturn(page());

        mockMvc.perform(get("/api/projects/{projectId}/nodes", PROJECT_ID)
                        .param("graphState", "UNATTACHED")
                        .session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.items[0].nodeId").value(NODE_ID))
                .andExpect(jsonPath("$.data.items[0].content").doesNotExist())
                .andExpect(jsonPath("$.data.page").value(0))
                .andExpect(jsonPath("$.data.size").value(20));

        verify(graphQueryService).getUnattachedNodes(PROJECT_ID, MEMBER_ID, "UNATTACHED", 0, 20);
    }

    @Test
    void delegatesGraphStateValidationToServiceAndRejectsOversizedPage() throws Exception {
        when(graphQueryService.getUnattachedNodes(PROJECT_ID, MEMBER_ID, "ACTIVE", 0, 20))
                .thenThrow(new CustomException(GraphQueryErrorCode.INVALID_GRAPH_STATE_QUERY));

        mockMvc.perform(get("/api/projects/{projectId}/nodes", PROJECT_ID)
                        .param("graphState", "ACTIVE")
                        .session(loginSession()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_GRAPH_STATE_QUERY"));
        mockMvc.perform(get("/api/projects/{projectId}/nodes", PROJECT_ID)
                        .param("graphState", "UNATTACHED")
                        .param("size", "51")
                        .session(loginSession()))
                .andExpect(status().isBadRequest());

        verify(graphQueryService, never()).getUnattachedNodes(
                eq(PROJECT_ID), eq(MEMBER_ID), eq("UNATTACHED"), anyInt(), eq(51)
        );
    }

    @Test
    void rejectsBlankGraphStateAndInvalidPageBounds() throws Exception {
        when(graphQueryService.getUnattachedNodes(PROJECT_ID, MEMBER_ID, "", 0, 20))
                .thenThrow(new CustomException(GraphQueryErrorCode.INVALID_GRAPH_STATE_QUERY));

        mockMvc.perform(get("/api/projects/{projectId}/nodes", PROJECT_ID)
                        .param("graphState", "")
                        .session(loginSession()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_GRAPH_STATE_QUERY"));
        mockMvc.perform(get("/api/projects/{projectId}/nodes", PROJECT_ID)
                        .param("graphState", "UNATTACHED")
                        .param("page", "-1")
                        .session(loginSession()))
                .andExpect(status().isBadRequest());
        mockMvc.perform(get("/api/projects/{projectId}/nodes", PROJECT_ID)
                        .param("graphState", "UNATTACHED")
                        .param("size", "0")
                        .session(loginSession()))
                .andExpect(status().isBadRequest());
    }

    @Test
    void servesDetailMergedSourcesAndMeetingNodes() throws Exception {
        when(graphQueryService.getNodeDetail(PROJECT_ID, NODE_ID, MEMBER_ID)).thenReturn(detail());
        when(graphQueryService.getMergedSources(PROJECT_ID, NODE_ID, MEMBER_ID)).thenReturn(
                new GraphMergedSourcesResponse(PROJECT_ID, 5, Instant.parse("2026-08-05T00:00:00Z"), NODE_ID, List.of())
        );
        when(graphQueryService.getMeetingNodes(PROJECT_ID, 33, MEMBER_ID, 0, 20)).thenReturn(page());

        mockMvc.perform(get("/api/projects/{projectId}/nodes/{nodeId}", PROJECT_ID, NODE_ID).session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.node.content").value("content"))
                .andExpect(jsonPath("$.data.node.evidences").isArray());
        mockMvc.perform(get("/api/projects/{projectId}/nodes/{nodeId}/merged-sources", PROJECT_ID, NODE_ID)
                        .session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.targetNodeId").value(NODE_ID));
        mockMvc.perform(get("/api/projects/{projectId}/meetings/{meetingId}/nodes", PROJECT_ID, 33)
                        .session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.items[0].nodeId").value(NODE_ID));
    }

    @Test
    void requiresLoginBeforeCallingQueryService() throws Exception {
        mockMvc.perform(get("/api/projects/{projectId}/nodes/tree", PROJECT_ID))
                .andExpect(status().isUnauthorized());

        verify(graphQueryService, never()).getTree(PROJECT_ID, MEMBER_ID);
    }

    private GraphTreeResponse tree() {
        GraphTreeNodeResponse graphNode = new GraphTreeNodeResponse(
                NODE_ID,
                GraphTreeNodeKind.GRAPH_NODE,
                "Backend API",
                GraphNodeCategory.BACKEND,
                GraphNodeType.DECISION,
                33,
                3L,
                Instant.parse("2026-08-05T00:00:01Z"),
                List.of()
        );
        GraphTreeNodeResponse category = new GraphTreeNodeResponse(
                "category:BACKEND", GraphTreeNodeKind.CATEGORY_ROOT, "Backend", GraphNodeCategory.BACKEND,
                null, null, null, null, List.of(graphNode)
        );
        return new GraphTreeResponse(
                PROJECT_ID,
                5,
                Instant.parse("2026-08-05T00:00:00Z"),
                new GraphTreeNodeResponse(
                        "project:11", GraphTreeNodeKind.PROJECT_ROOT, "project", null,
                        null, null, null, null,
                        List.of(category, category, category, category, category, category, category)
                )
        );
    }

    private GraphNodePageResponse page() {
        return new GraphNodePageResponse(
                PROJECT_ID, 5, Instant.parse("2026-08-05T00:00:00Z"),
                List.of(new GraphNodeSummaryResponse(
                        NODE_ID, 33, null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND,
                        GraphNodeState.UNATTACHED, "title", null, 2,
                        Instant.parse("2026-08-05T00:00:00Z"), Instant.parse("2026-08-05T00:00:01Z")
                )),
                0, 20, 1, 1
        );
    }

    private GraphNodeDetailResponse detail() {
        return new GraphNodeDetailResponse(
                PROJECT_ID, 5, Instant.parse("2026-08-05T00:00:00Z"),
                new GraphNodeDetailItemResponse(
                        NODE_ID, 33, null, null, GraphNodeType.DECISION, GraphNodeCategory.BACKEND,
                        GraphNodeState.ACTIVE, "title", "content", null, 2,
                        Instant.parse("2026-08-05T00:00:00Z"), Instant.parse("2026-08-05T00:00:01Z"), List.of()
                )
        );
    }

    private MockHttpSession loginSession() {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SessionConst.SESSION_LOGIN_MEMBER, LoginMember.builder()
                .id(MEMBER_ID)
                .name("member")
                .email("member@example.com")
                .build());
        return session;
    }
}
