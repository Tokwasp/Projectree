package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.controller.request.GoogleLoginRequest;
import com.ssafy.projectree.domain.member.controller.response.GoogleLoginResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleTokenResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleUserInfoResponse;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockHttpSession;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.tuple;
import static org.mockito.BDDMockito.given;

class AuthServiceTest extends IntegrationTestSupport {

    private static final String REDIRECT_URI = "http://localhost:3000/login/oauth2/code/google";

    @Autowired
    private AuthService authService;

    @Autowired
    private MemberRepository memberRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @DisplayName("가입 이력이 없는 이메일로 구글 로그인을 하면 회원을 새로 저장하고 세션에 로그인 회원 정보를 담는다.")
    @Test
    void googleLogin() {
        // given
        GoogleLoginRequest request = createRequest("authorization-code");
        MockHttpSession session = new MockHttpSession();

        given(googleOAuthClient.getUserAccessToken("authorization-code", REDIRECT_URI))
                .willReturn(createToken("google-access-token"));
        given(googleOAuthClient.getUserInfo("google-access-token"))
                .willReturn(createUserInfo("ssafy@gmail.com", "김싸피"));

        // when
        GoogleLoginResponse response = authService.googleLogin(request, session);

        // then
        assertThat(response)
                .extracting("name", "imageUrl")
                .contains("김싸피", "");

        entityManager.flush();
        entityManager.clear();

        List<Member> members = memberRepository.findAll();
        assertThat(members).hasSize(1)
                .extracting("email", "name")
                .containsExactlyInAnyOrder(
                        tuple("ssafy@gmail.com", "김싸피")
                );
        assertThat(session.getAttribute("loginMember"))
                .extracting("id", "name", "email")
                .containsExactly(members.get(0).getId(), "김싸피", "ssafy@gmail.com");
    }

    @DisplayName("이미 가입된 이메일로 구글 로그인을 하면 회원을 새로 저장하지 않고 기존 회원으로 로그인한다.")
    @Test
    void googleLoginWithRegisteredEmail() {
        // given
        Member savedMember = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));

        GoogleLoginRequest request = createRequest("authorization-code");
        MockHttpSession session = new MockHttpSession();

        given(googleOAuthClient.getUserAccessToken("authorization-code", REDIRECT_URI))
                .willReturn(createToken("google-access-token"));
        given(googleOAuthClient.getUserInfo("google-access-token"))
                .willReturn(createUserInfo("ssafy@gmail.com", "구글에서 바뀐 이름"));

        // when
        GoogleLoginResponse response = authService.googleLogin(request, session);

        // then
        assertThat(response)
                .extracting("name", "imageUrl")
                .contains("김싸피", "");

        entityManager.flush();
        entityManager.clear();

        List<Member> members = memberRepository.findAll();
        assertThat(members).hasSize(1)
                .extracting("email", "name")
                .containsExactlyInAnyOrder(
                        tuple("ssafy@gmail.com", "김싸피")
                );
        assertThat(session.getAttribute("loginMember"))
                .extracting("id", "name", "email")
                .containsExactly(savedMember.getId(), "김싸피", "ssafy@gmail.com");
    }

    private GoogleLoginRequest createRequest(String code) {
        return GoogleLoginRequest.builder()
                .code(code)
                .redirectUri(REDIRECT_URI)
                .build();
    }

    private GoogleTokenResponse createToken(String accessToken) {
        return GoogleTokenResponse.builder()
                .accessToken(accessToken)
                .build();
    }

    private GoogleUserInfoResponse createUserInfo(String email, String name) {
        return GoogleUserInfoResponse.builder()
                .sub("google-sub")
                .email(email)
                .emailVerified(true)
                .name(name)
                .picture("https://lh3.googleusercontent.com/profile.png")
                .build();
    }

    private Member createMember(String email, String name) {
        return Member.builder()
                .email(email)
                .name(name)
                .build();
    }

}
