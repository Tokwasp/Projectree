package com.ssafy.projectree.domain.meeting.result.graph.command;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateAcceptedResponse;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateItem;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateRequest;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.BatchNodeContentUpdateResponse;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteAcceptedResponse;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteRequest;
import com.ssafy.projectree.domain.meeting.result.graph.delete.dto.GraphNodeDeleteStatusResponse;
import com.ssafy.projectree.domain.meeting.result.graph.delete.NodeDeleteCommandStatus;
import com.ssafy.projectree.domain.member.LoginMember;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;

import java.util.UUID;
import java.util.List;
import java.time.LocalDateTime;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.doThrow;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GraphNodeCommandControllerTest extends ControllerTestSupport {

    @Test
    void acceptsUpdateAndPassesAuthenticatedMemberId() throws Exception {
        int projectId = 1;
        int memberId = 15;
        String nodeId = UUID.randomUUID().toString();
        UUID commandId = UUID.randomUUID();
        NodeContentUpdateRequest request = new NodeContentUpdateRequest(" title ", null, 3L);
        when(graphNodeUpdateService.update(projectId, nodeId, memberId, request))
                .thenReturn(NodeContentUpdateAcceptedResponse.pending(commandId, nodeId, 3));

        mockMvc.perform(patch("/api/projects/{projectId}/nodes/{nodeId}", projectId, nodeId)
                        .session(session(memberId))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.commandId").value(commandId.toString()))
                .andExpect(jsonPath("$.data.nodeId").value(nodeId))
                .andExpect(jsonPath("$.data.expectedNodeVersion").value(3))
                .andExpect(jsonPath("$.data.status").value("PENDING"));

        verify(graphNodeUpdateService).update(projectId, nodeId, memberId, request);
    }

    @Test
    void rejectsMissingExpectedVersion() throws Exception {
        mockMvc.perform(patch("/api/projects/1/nodes/{nodeId}", UUID.randomUUID())
                        .session(session(15))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"title\":\"title\"}"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void acceptsBatchUpdateAndReturnsNodeCounts() throws Exception {
        int projectId = 1;
        int memberId = 15;
        String firstNodeId = UUID.randomUUID().toString();
        String secondNodeId = UUID.randomUUID().toString();
        UUID commandId = UUID.randomUUID();
        BatchNodeContentUpdateRequest request = new BatchNodeContentUpdateRequest(List.of(
                new BatchNodeContentUpdateItem(firstNodeId, "first", 3L),
                new BatchNodeContentUpdateItem(secondNodeId, "second", 7L)
        ));
        when(graphNodeUpdateService.updateBatch(projectId, memberId, request))
                .thenReturn(BatchNodeContentUpdateResponse.pending(commandId, 2, 2));

        mockMvc.perform(patch("/api/projects/{projectId}/nodes", projectId)
                        .session(session(memberId))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.commandId").value(commandId.toString()))
                .andExpect(jsonPath("$.data.requestedNodeCount").value(2))
                .andExpect(jsonPath("$.data.changedNodeCount").value(2))
                .andExpect(jsonPath("$.data.status").value("PENDING"));

        verify(graphNodeUpdateService).updateBatch(projectId, memberId, request);
    }

    @Test
    void acceptsSingleItemBatchUpdate() throws Exception {
        int projectId = 1;
        int memberId = 15;
        BatchNodeContentUpdateRequest request = new BatchNodeContentUpdateRequest(List.of(
                new BatchNodeContentUpdateItem(
                        UUID.randomUUID().toString(), "updated", 3L
                )
        ));
        UUID commandId = UUID.randomUUID();
        when(graphNodeUpdateService.updateBatch(projectId, memberId, request))
                .thenReturn(BatchNodeContentUpdateResponse.pending(commandId, 1, 1));

        mockMvc.perform(patch("/api/projects/{projectId}/nodes", projectId)
                        .session(session(memberId))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.requestedNodeCount").value(1))
                .andExpect(jsonPath("$.data.changedNodeCount").value(1));
    }

    @Test
    void returnsBadRequestForDuplicateBatchNodeIds() throws Exception {
        int projectId = 1;
        int memberId = 15;
        String nodeId = UUID.randomUUID().toString();
        BatchNodeContentUpdateRequest request = new BatchNodeContentUpdateRequest(List.of(
                new BatchNodeContentUpdateItem(nodeId, "first", 3L),
                new BatchNodeContentUpdateItem(nodeId, "second", 3L)
        ));
        doThrow(new com.ssafy.projectree.global.exception.CustomException(
                GraphNodeUpdateErrorCode.NODE_UPDATE_DUPLICATE_NODE_ID
        )).when(graphNodeUpdateService).updateBatch(projectId, memberId, request);

        mockMvc.perform(patch("/api/projects/{projectId}/nodes", projectId)
                        .session(session(memberId))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @Test
    void returnsOkWhenBatchHasNoChanges() throws Exception {
        int projectId = 1;
        int memberId = 15;
        BatchNodeContentUpdateRequest request = new BatchNodeContentUpdateRequest(List.of(
                new BatchNodeContentUpdateItem(
                        UUID.randomUUID().toString(), "same", 3L
                )
        ));
        when(graphNodeUpdateService.updateBatch(projectId, memberId, request))
                .thenReturn(BatchNodeContentUpdateResponse.noChange(1));

        mockMvc.perform(patch("/api/projects/{projectId}/nodes", projectId)
                        .session(session(memberId))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.commandId").doesNotExist())
                .andExpect(jsonPath("$.data.requestedNodeCount").value(1))
                .andExpect(jsonPath("$.data.changedNodeCount").value(0))
                .andExpect(jsonPath("$.data.status").value("NO_CHANGE"));
    }

    @Test
    void rejectsInvalidBatchRequestBeforeCallingService() throws Exception {
        mockMvc.perform(patch("/api/projects/1/nodes")
                        .session(session(15))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"nodes\":[]}"))
                .andExpect(status().isBadRequest());

        mockMvc.perform(patch("/api/projects/1/nodes")
                        .session(session(15))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "nodes": [{
                                    "id": "not-a-uuid",
                                    "title": "",
                                    "expectedNodeVersion": 0
                                  }]
                                }
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(graphNodeUpdateService);
    }

    @Test
    void acceptsContentAtThe65535CharacterContractLimit() throws Exception {
        int projectId = 1;
        int memberId = 15;
        String nodeId = UUID.randomUUID().toString();
        UUID commandId = UUID.randomUUID();
        NodeContentUpdateRequest request =
                new NodeContentUpdateRequest(null, "가".repeat(65_535), 3L);
        when(graphNodeUpdateService.update(projectId, nodeId, memberId, request))
                .thenReturn(NodeContentUpdateAcceptedResponse.pending(commandId, nodeId, 3));

        mockMvc.perform(patch("/api/projects/{projectId}/nodes/{nodeId}", projectId, nodeId)
                        .session(session(memberId))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted());

        verify(graphNodeUpdateService).update(projectId, nodeId, memberId, request);
    }

    @Test
    void acceptsNodeDeleteAndPassesAuthenticatedMemberId() throws Exception {
        int projectId = 1;
        int memberId = 15;
        String nodeId = UUID.randomUUID().toString();
        UUID commandId = UUID.randomUUID();
        GraphNodeDeleteRequest request =
                new GraphNodeDeleteRequest(List.of(nodeId), 12);
        when(graphNodeDeleteService.deleteNodes(projectId, memberId, request))
                .thenReturn(GraphNodeDeleteAcceptedResponse.pending(
                        commandId,
                        projectId,
                        request.nodeIds(),
                        request.expectedGraphVersion()
                ));

        mockMvc.perform(post("/api/projects/{projectId}/nodes/delete", projectId)
                        .session(session(memberId))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.data.commandId").value(commandId.toString()))
                .andExpect(jsonPath("$.data.projectId").value(projectId))
                .andExpect(jsonPath("$.data.nodeIds[0]").value(nodeId))
                .andExpect(jsonPath("$.data.expectedGraphVersion").value(12))
                .andExpect(jsonPath("$.data.status").value("PENDING"));

        verify(graphNodeDeleteService).deleteNodes(projectId, memberId, request);
    }

    @Test
    void rejectsInvalidNodeDeleteRequestBeforeCallingService() throws Exception {
        mockMvc.perform(post("/api/projects/1/nodes/delete")
                        .session(session(15))
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "nodeIds": [],
                                  "expectedGraphVersion": -1
                                }
                                """))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(graphNodeDeleteService);
    }

    @Test
    void returnsNodeDeleteCommandStatus() throws Exception {
        int projectId = 1;
        int memberId = 15;
        UUID commandId = UUID.randomUUID();
        String nodeId = UUID.randomUUID().toString();
        LocalDateTime requestedAt = LocalDateTime.of(2026, 8, 7, 5, 0);
        GraphNodeDeleteStatusResponse response = new GraphNodeDeleteStatusResponse(
                commandId,
                projectId,
                List.of(nodeId),
                12,
                null,
                NodeDeleteCommandStatus.PENDING,
                null,
                requestedAt,
                null
        );
        when(graphNodeDeleteStatusService.getStatus(projectId, commandId, memberId))
                .thenReturn(response);

        mockMvc.perform(get(
                        "/api/projects/{projectId}/nodes/delete-commands/{commandId}",
                        projectId,
                        commandId
                ).session(session(memberId)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.commandId").value(commandId.toString()))
                .andExpect(jsonPath("$.data.projectId").value(projectId))
                .andExpect(jsonPath("$.data.nodeIds[0]").value(nodeId))
                .andExpect(jsonPath("$.data.status").value("PENDING"))
                .andExpect(jsonPath("$.data.reason").doesNotExist())
                .andExpect(jsonPath("$.data.resultGraphVersion").doesNotExist())
                .andExpect(jsonPath("$.data.completedAt").doesNotExist());

        verify(graphNodeDeleteStatusService)
                .getStatus(projectId, commandId, memberId);
    }

    @Test
    void rejectsMalformedDeleteCommandId() throws Exception {
        mockMvc.perform(get(
                        "/api/projects/1/nodes/delete-commands/not-a-uuid"
                ).session(session(15)))
                .andExpect(status().isBadRequest());

        verifyNoInteractions(graphNodeDeleteStatusService);
    }

    private MockHttpSession session(int memberId) {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SESSION_LOGIN_MEMBER, LoginMember.builder()
                .id(memberId)
                .name("member")
                .email("member@example.com")
                .build());
        return session;
    }
}
