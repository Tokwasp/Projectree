package com.ssafy.projectree.domain.member.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.controller.request.GoogleLoginRequest;
import com.ssafy.projectree.domain.member.controller.request.NaverLoginRequest;
import com.ssafy.projectree.domain.member.controller.response.GoogleLoginResponse;
import com.ssafy.projectree.domain.member.controller.response.NaverLoginResponse;
import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;
import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultHandlers.print;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class AuthControllerTest extends ControllerTestSupport {

    @DisplayName("authorization code로 구글 로그인을 하면 회원의 이름과 프로필 이미지 URL을 응답한다.")
    @Test
    void googleLogin() throws Exception {
        // given
        GoogleLoginRequest request = GoogleLoginRequest.builder()
                .code("authorization-code")
                .redirectUri("http://localhost:3000/login/oauth2/code/google")
                .build();

        Member member = Member.builder()
                .email("ssafy@gmail.com")
                .name("김싸피")
                .build();

        when(authService.googleLogin(any(GoogleLoginRequest.class), any(HttpSession.class)))
                .thenReturn(GoogleLoginResponse.from(member));

        // when // then
        mockMvc.perform(
                        post("/api/auth/google")
                                .content(objectMapper.writeValueAsString(request))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data.name").value("김싸피"))
                .andExpect(jsonPath("$.data.imageUrl").value(""))
        ;
    }

    @DisplayName("구글 로그인을 할 때 authorization code는 필수값이다.")
    @Test
    void googleLoginWithoutCode() throws Exception {
        // given
        GoogleLoginRequest request = GoogleLoginRequest.builder()
                .redirectUri("http://localhost:3000/login/oauth2/code/google")
                .build();

        // when // then
        mockMvc.perform(
                        post("/api/auth/google")
                                .content(objectMapper.writeValueAsString(request))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isBadRequest())
        ;
    }

    @DisplayName("구글 로그인을 할 때 redirectUri는 필수값이다.")
    @Test
    void googleLoginWithoutRedirectUri() throws Exception {
        // given
        GoogleLoginRequest request = GoogleLoginRequest.builder()
                .code("authorization-code")
                .build();

        // when // then
        mockMvc.perform(
                        post("/api/auth/google")
                                .content(objectMapper.writeValueAsString(request))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isBadRequest())
        ;
    }

    @DisplayName("구글 로그인을 할 때 authorization code는 공백일 수 없다.")
    @Test
    void googleLoginWithBlankCode() throws Exception {
        // given
        GoogleLoginRequest request = GoogleLoginRequest.builder()
                .code("   ")
                .redirectUri("http://localhost:3000/login/oauth2/code/google")
                .build();

        // when // then
        mockMvc.perform(
                        post("/api/auth/google")
                                .content(objectMapper.writeValueAsString(request))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isBadRequest())
        ;
    }

    @DisplayName("authorization code로 네이버 로그인을 하면 회원의 이름과 이메일, 프로필 이미지 URL을 응답한다.")
    @Test
    void naverLogin() throws Exception {
        // given
        NaverLoginRequest request = NaverLoginRequest.builder()
                .code("authorization-code")
                .state("csrf-state")
                .build();

        Member member = Member.builder()
                .email("ssafy@naver.com")
                .name("김싸피")
                .build();

        when(authService.naverLogin(any(NaverLoginRequest.class), any(HttpSession.class)))
                .thenReturn(NaverLoginResponse.from(member));

        // when // then
        mockMvc.perform(
                        post("/api/auth/naver")
                                .content(objectMapper.writeValueAsString(request))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data.name").value("김싸피"))
                .andExpect(jsonPath("$.data.email").value("ssafy@naver.com"))
                .andExpect(jsonPath("$.data.imageUrl").value(""))
        ;
    }

    @DisplayName("네이버 로그인을 할 때 authorization code는 필수값이다.")
    @Test
    void naverLoginWithoutCode() throws Exception {
        // given
        NaverLoginRequest request = NaverLoginRequest.builder()
                .state("csrf-state")
                .build();

        // when // then
        mockMvc.perform(
                        post("/api/auth/naver")
                                .content(objectMapper.writeValueAsString(request))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isBadRequest())
        ;
    }

    @DisplayName("네이버 로그인을 할 때 state는 필수값이다.")
    @Test
    void naverLoginWithoutState() throws Exception {
        // given
        NaverLoginRequest request = NaverLoginRequest.builder()
                .code("authorization-code")
                .build();

        // when // then
        mockMvc.perform(
                        post("/api/auth/naver")
                                .content(objectMapper.writeValueAsString(request))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isBadRequest())
        ;
    }

    @DisplayName("네이버 로그인을 할 때 authorization code는 공백일 수 없다.")
    @Test
    void naverLoginWithBlankCode() throws Exception {
        // given
        NaverLoginRequest request = NaverLoginRequest.builder()
                .code("   ")
                .state("csrf-state")
                .build();

        // when // then
        mockMvc.perform(
                        post("/api/auth/naver")
                                .content(objectMapper.writeValueAsString(request))
                                .contentType(MediaType.APPLICATION_JSON)
                )
                .andDo(print())
                .andExpect(status().isBadRequest())
        ;
    }

    @DisplayName("로그인한 회원이 로그아웃하면 세션이 무효화된다.")
    @Test
    void logout() throws Exception {
        // given
        MockHttpSession session = loginSession();

        // when // then
        mockMvc.perform(
                        post("/api/auth/logout")
                                .session(session)
                )
                .andDo(print())
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data").isEmpty())
        ;

        assertThat(session.isInvalid()).isTrue();
    }

    @DisplayName("세션 없이 로그아웃을 요청하면 401을 응답한다.")
    @Test
    void logoutWithoutSession() throws Exception {
        // when // then
        mockMvc.perform(
                        post("/api/auth/logout")
                )
                .andDo(print())
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"))
        ;
    }

    @DisplayName("세션에 로그인 정보가 없으면 로그아웃 시 401을 응답하고 세션을 무효화하지 않는다.")
    @Test
    void logoutWithSessionButNoLoginMember() throws Exception {
        // given
        MockHttpSession session = new MockHttpSession();

        // when // then
        mockMvc.perform(
                        post("/api/auth/logout")
                                .session(session)
                )
                .andDo(print())
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"))
        ;

        assertThat(session.isInvalid()).isFalse();
    }

    private MockHttpSession loginSession() {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SESSION_LOGIN_MEMBER, LoginMember.builder()
                .id(1)
                .name("김싸피")
                .email("ssafy@gmail.com")
                .build());
        return session;
    }

}
