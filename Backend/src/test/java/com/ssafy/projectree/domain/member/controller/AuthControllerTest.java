package com.ssafy.projectree.domain.member.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.controller.request.GoogleLoginRequest;
import com.ssafy.projectree.domain.member.controller.response.GoogleLoginResponse;
import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;

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

}
