package com.ssafy.projectree.domain.member.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.member.controller.response.MemberSearchResponse;
import com.ssafy.projectree.global.config.session.SessionConst;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class MemberControllerTest extends ControllerTestSupport {

    @DisplayName("로그인한 회원은 이메일이 완전히 일치하는 회원을 조회할 수 있다.")
    @Test
    void findByEmail() throws Exception {
        // given
        given(memberService.findByEmail("invitee@example.com"))
                .willReturn(createResponse());

        // when & then
        mockMvc.perform(get("/api/members")
                        .param("email", "invitee@example.com")
                        .session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.data.memberId").value(2))
                .andExpect(jsonPath("$.data.name").value("초대 대상"))
                .andExpect(jsonPath("$.data.email").value("invitee@example.com"));
    }

    @DisplayName("이메일 파라미터 없이 회원을 조회하면 400을 응답한다.")
    @Test
    void findByEmail_withoutEmail_returnsBadRequest() throws Exception {
        // when & then
        mockMvc.perform(get("/api/members").session(loginSession()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));
    }

    @DisplayName("로그인하지 않고 회원을 조회하면 401을 응답한다.")
    @Test
    void findByEmail_withoutLogin_returnsUnauthorized() throws Exception {
        // when & then
        mockMvc.perform(get("/api/members").param("email", "invitee@example.com"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"));
    }

    private MemberSearchResponse createResponse() {
        return MemberSearchResponse.of(2, "초대 대상", "invitee@example.com");
    }

    private MockHttpSession loginSession() {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SessionConst.SESSION_LOGIN_MEMBER, LoginMember.builder()
                .id(1)
                .name("초대자")
                .email("inviter@example.com")
                .build());
        return session;
    }
}
