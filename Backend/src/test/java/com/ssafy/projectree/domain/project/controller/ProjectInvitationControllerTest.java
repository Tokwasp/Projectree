package com.ssafy.projectree.domain.project.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.mail.entity.MailSendStatus;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.project.controller.dto.response.InviteResultsResponse;
import com.ssafy.projectree.domain.project.controller.dto.response.InviteTargetResponse;
import com.ssafy.projectree.domain.project.controller.dto.response.PendingInvitationResponse;
import com.ssafy.projectree.domain.project.service.result.InviteResult;
import com.ssafy.projectree.global.config.session.SessionConst;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;

import java.util.List;

import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class ProjectInvitationControllerTest extends ControllerTestSupport {

    @Test
    void invite_returnsResults() throws Exception {
        given(projectInvitationService.invite(anyInt(), anyInt(), anyList()))
                .willReturn(InviteResultsResponse.from(List.of(
                        InviteTargetResponse.of(20, InviteResult.INVITED)
                )));

        mockMvc.perform(post("/api/projects/1/invitations")
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"inviteeMemberIds\":[20]}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.data.results[0].inviteeMemberId").value(20))
                .andExpect(jsonPath("$.data.results[0].result").value("INVITED"));
    }

    @Test
    void getPendingInvitations_returnsPendingInvitations() throws Exception {
        PendingInvitationResponse pendingInvitation = mock(PendingInvitationResponse.class);
        given(pendingInvitation.getInvitationId()).willReturn(3);
        given(pendingInvitation.getInviteeName()).willReturn("초대 대상");
        given(pendingInvitation.getMailSendStatus()).willReturn(MailSendStatus.NOT_REQUESTED);
        given(projectInvitationService.getPendingInvitations(1, 10))
                .willReturn(List.of(pendingInvitation));

        mockMvc.perform(get("/api/projects/1/invitations").session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data[0].invitationId").value(3))
                .andExpect(jsonPath("$.data[0].inviteeName").value("초대 대상"))
                .andExpect(jsonPath("$.data[0].mailSendStatus").value("NOT_REQUESTED"));
    }

    @Test
    void cancelInvitation_returnsNoContent() throws Exception {
        mockMvc.perform(delete("/api/projects/1/invitations/3").session(loginSession()))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""));
    }

    @Test
    void invite_withEmptyInvitees_returnsBadRequest() throws Exception {
        assertInvalidCreateRequest("{\"inviteeMemberIds\":[]}");
    }

    @Test
    void invite_withTooManyInvitees_returnsBadRequest() throws Exception {
        assertInvalidCreateRequest("{\"inviteeMemberIds\":[1,2,3,4,5,6,7,8,9,10,11]}");
    }

    @Test
    void invite_withDuplicateInvitees_returnsBadRequest() throws Exception {
        assertInvalidCreateRequest("{\"inviteeMemberIds\":[20,20]}");
    }

    @Test
    void projectInvitationEndpoints_withoutLogin_returnUnauthorized() throws Exception {
        mockMvc.perform(post("/api/projects/1/invitations")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"inviteeMemberIds\":[20]}"))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(get("/api/projects/1/invitations"))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(delete("/api/projects/1/invitations/3"))
                .andExpect(status().isUnauthorized());
    }

    private void assertInvalidCreateRequest(String requestBody) throws Exception {
        mockMvc.perform(post("/api/projects/1/invitations")
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(requestBody))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));
    }

    private MockHttpSession loginSession() {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SessionConst.SESSION_LOGIN_MEMBER, LoginMember.builder()
                .id(10)
                .name("로그인 회원")
                .email("login@example.com")
                .build());
        return session;
    }
}
