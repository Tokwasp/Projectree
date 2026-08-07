package com.ssafy.projectree.domain.meeting.result.graph.command;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateAcceptedResponse;
import com.ssafy.projectree.domain.meeting.result.graph.command.dto.NodeContentUpdateRequest;
import com.ssafy.projectree.domain.member.LoginMember;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;

import java.util.UUID;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
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
