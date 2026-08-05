package com.ssafy.projectree.domain.member.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.member.controller.response.MemberSearchResponse;
import com.ssafy.projectree.domain.member.controller.response.MemberProfileResponse;
import com.ssafy.projectree.global.config.session.SessionConst;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;

import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.BDDMockito.willThrow;
import static org.mockito.Mockito.never;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class MemberControllerTest extends ControllerTestSupport {

    @DisplayName("로그인한 회원은 자신의 프로필을 조회할 수 있다.")
    @Test
    void findMyProfile() throws Exception {
        given(memberService.findProfile(1))
                .willReturn(MemberProfileResponse.of(1, "초대자", "inviter@example.com"));

        mockMvc.perform(get("/api/members/me").session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.data.memberId").value(1))
                .andExpect(jsonPath("$.data.name").value("초대자"))
                .andExpect(jsonPath("$.data.email").value("inviter@example.com"));
    }

    @DisplayName("로그인하지 않고 프로필을 조회하면 401을 응답한다.")
    @Test
    void findMyProfile_withoutLogin_returnsUnauthorized() throws Exception {
        mockMvc.perform(get("/api/members/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"));
    }

    @DisplayName("세션에 로그인 정보가 없으면 프로필 조회 시 401을 응답한다.")
    @Test
    void findMyProfile_withSessionButNoLoginMember_returnsUnauthorized() throws Exception {
        mockMvc.perform(get("/api/members/me").session(new MockHttpSession()))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"));
    }

    @DisplayName("세션은 유효하지만 회원이 없으면 프로필 조회 시 404를 응답한다.")
    @Test
    void findMyProfile_whenMemberRemoved_returnsNotFound() throws Exception {
        given(memberService.findProfile(1))
                .willThrow(new CustomException(CommonErrorCode.MEMBER_NOT_FOUND));

        mockMvc.perform(get("/api/members/me").session(loginSession()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("MEMBER_NOT_FOUND"));
    }

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

    @DisplayName("프로필 이미지가 있는 회원은 이미지 URL을 함께 응답한다.")
    @Test
    void findMyProfile_withProfileImage_returnsUrl() throws Exception {
        given(memberService.findProfile(1))
                .willReturn(MemberProfileResponse.of(
                        1, "초대자", "inviter@example.com", "https://cdn.example.com/profile/1.png"
                ));

        mockMvc.perform(get("/api/members/me").session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.profileImageUrl")
                        .value("https://cdn.example.com/profile/1.png"));
    }

    @DisplayName("프로필 이미지를 등록하지 않은 회원은 이미지 URL을 null로 응답한다.")
    @Test
    void findMyProfile_withoutProfileImage_returnsNullUrl() throws Exception {
        given(memberService.findProfile(1))
                .willReturn(MemberProfileResponse.of(1, "초대자", "inviter@example.com"));

        mockMvc.perform(get("/api/members/me").session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.profileImageUrl").isEmpty());
    }

    @DisplayName("로그인한 회원은 자신의 계정을 탈퇴할 수 있고 세션의 회원 식별자로 탈퇴가 실행된다.")
    @Test
    void deleteMember() throws Exception {
        // when & then
        mockMvc.perform(delete("/api/members/me").session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.data").isEmpty());

        then(memberService).should().deleteMember(1);
    }

    @DisplayName("로그인하지 않고 탈퇴를 요청하면 401을 응답하고 탈퇴를 실행하지 않는다.")
    @Test
    void deleteMember_withoutLogin_returnsUnauthorized() throws Exception {
        // when & then
        mockMvc.perform(delete("/api/members/me"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"));

        then(memberService).should(never()).deleteMember(anyInt());
    }

    @DisplayName("세션은 유효하지만 회원이 없으면 탈퇴 시 404를 응답한다.")
    @Test
    void deleteMember_whenMemberRemoved_returnsNotFound() throws Exception {
        // given
        willThrow(new CustomException(CommonErrorCode.MEMBER_NOT_FOUND))
                .given(memberService).deleteMember(1);

        // when & then
        mockMvc.perform(delete("/api/members/me").session(loginSession()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("MEMBER_NOT_FOUND"));
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
