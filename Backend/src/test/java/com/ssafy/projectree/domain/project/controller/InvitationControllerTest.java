package com.ssafy.projectree.domain.project.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.project.controller.dto.response.InvitationLandingResponse;
import com.ssafy.projectree.domain.project.entity.InvitationStatus;
import com.ssafy.projectree.domain.project.exception.InvitationErrorCode;
import com.ssafy.projectree.global.config.session.SessionConst;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;

import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class InvitationControllerTest extends ControllerTestSupport {

    @Test
    void getLanding_returnsInvitationLanding() throws Exception {
        InvitationLandingResponse landing = mock(InvitationLandingResponse.class);
        given(landing.getProjectTitle()).willReturn("프로젝트");
        given(landing.getInviterName()).willReturn("초대자");
        given(landing.getStatus()).willReturn(InvitationStatus.PENDING);
        given(landing.isExpired()).willReturn(false);
        given(projectInvitationService.getLanding("token", 20)).willReturn(landing);

        mockMvc.perform(get("/api/invitations/token").session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.projectTitle").value("프로젝트"))
                .andExpect(jsonPath("$.data.inviterName").value("초대자"))
                .andExpect(jsonPath("$.data.status").value("PENDING"))
                .andExpect(jsonPath("$.data.expired").value(false));
    }

    @Test
    void acceptInvitation_returnsProjectId() throws Exception {
        given(projectInvitationService.acceptInvitation("token", 20)).willReturn(1);

        mockMvc.perform(post("/api/invitations/token/accept").session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.projectId").value(1));
    }

    @Test
    void rejectInvitation_returnsNoContent() throws Exception {
        mockMvc.perform(post("/api/invitations/token/reject").session(loginSession()))
                .andExpect(status().isNoContent())
                .andExpect(content().string(""));
    }

    @Test
    void invitationEndpoints_withoutLogin_returnUnauthorized() throws Exception {
        mockMvc.perform(get("/api/invitations/token"))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(post("/api/invitations/token/accept"))
                .andExpect(status().isUnauthorized());
        mockMvc.perform(post("/api/invitations/token/reject"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void acceptInvitation_expiredInvitation_returnsGone() throws Exception {
        given(projectInvitationService.acceptInvitation(anyString(), anyInt()))
                .willThrow(new CustomException(InvitationErrorCode.INVITATION_EXPIRED));

        mockMvc.perform(post("/api/invitations/expired-token/accept").session(loginSession()))
                .andExpect(status().isGone())
                .andExpect(jsonPath("$.errorCode").value("INVITATION_EXPIRED"));
    }

    private MockHttpSession loginSession() {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SessionConst.SESSION_LOGIN_MEMBER, LoginMember.builder()
                .id(20)
                .name("초대 대상")
                .email("invitee@example.com")
                .build());
        return session;
    }
}
