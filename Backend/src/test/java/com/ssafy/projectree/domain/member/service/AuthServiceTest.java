package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.exception.AuthErrorCode;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.controller.request.GoogleLoginRequest;
import com.ssafy.projectree.domain.member.controller.request.NaverLoginRequest;
import com.ssafy.projectree.domain.member.controller.response.GoogleLoginResponse;
import com.ssafy.projectree.domain.member.controller.response.NaverLoginResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleTokenResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleUserInfoResponse;
import com.ssafy.projectree.domain.member.controller.response.session.NaverTokenResponse;
import com.ssafy.projectree.domain.member.controller.response.session.NaverUserInfoResponse;
import com.ssafy.projectree.global.exception.CustomException;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.mock.web.MockHttpSession;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.tuple;
import static org.mockito.BDDMockito.given;

class AuthServiceTest extends IntegrationTestSupport {

    private static final String REDIRECT_URI = "http://localhost:3000/login/oauth2/code/google";
    private static final String STATE = "csrf-state";

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

    @DisplayName("가입 이력이 없는 이메일로 네이버 로그인을 하면 회원을 새로 저장하고 세션에 로그인 회원 정보를 담는다.")
    @Test
    void naverLogin() {
        // given
        NaverLoginRequest request = createNaverRequest("authorization-code");
        MockHttpSession session = new MockHttpSession();

        given(naverOAuthClient.getUserAccessToken("authorization-code", STATE))
                .willReturn(createNaverToken("naver-access-token"));
        given(naverOAuthClient.getUserInfo("naver-access-token"))
                .willReturn(createNaverUserInfo("ssafy@naver.com", "김싸피"));

        // when
        NaverLoginResponse response = authService.naverLogin(request, session);

        // then
        assertThat(response)
                .extracting("name", "email", "imageUrl")
                .contains("김싸피", "ssafy@naver.com", "");

        entityManager.flush();
        entityManager.clear();

        List<Member> members = memberRepository.findAll();
        assertThat(members).hasSize(1)
                .extracting("email", "name")
                .containsExactlyInAnyOrder(
                        tuple("ssafy@naver.com", "김싸피")
                );
        assertThat(session.getAttribute("loginMember"))
                .extracting("id", "name", "email")
                .containsExactly(members.get(0).getId(), "김싸피", "ssafy@naver.com");
    }

    @DisplayName("이미 가입된 이메일로 네이버 로그인을 하면 회원을 새로 저장하지 않고 기존 회원으로 로그인한다.")
    @Test
    void naverLoginWithRegisteredEmail() {
        // given
        Member savedMember = memberRepository.save(createMember("ssafy@naver.com", "김싸피"));

        NaverLoginRequest request = createNaverRequest("authorization-code");
        MockHttpSession session = new MockHttpSession();

        given(naverOAuthClient.getUserAccessToken("authorization-code", STATE))
                .willReturn(createNaverToken("naver-access-token"));
        given(naverOAuthClient.getUserInfo("naver-access-token"))
                .willReturn(createNaverUserInfo("ssafy@naver.com", "네이버에서 바뀐 이름"));

        // when
        NaverLoginResponse response = authService.naverLogin(request, session);

        // then
        assertThat(response)
                .extracting("name", "email", "imageUrl")
                .contains("김싸피", "ssafy@naver.com", "");

        entityManager.flush();
        entityManager.clear();

        List<Member> members = memberRepository.findAll();
        assertThat(members).hasSize(1)
                .extracting("email", "name")
                .containsExactlyInAnyOrder(
                        tuple("ssafy@naver.com", "김싸피")
                );
        assertThat(session.getAttribute("loginMember"))
                .extracting("id", "name", "email")
                .containsExactly(savedMember.getId(), "김싸피", "ssafy@naver.com");
    }

    @DisplayName("구글로 가입한 이메일과 같은 이메일로 네이버 로그인을 하면 같은 회원으로 로그인한다.")
    @Test
    void naverLoginWithGoogleRegisteredEmail() {
        // given
        MockHttpSession googleSession = new MockHttpSession();

        given(googleOAuthClient.getUserAccessToken("google-authorization-code", REDIRECT_URI))
                .willReturn(createToken("google-access-token"));
        given(googleOAuthClient.getUserInfo("google-access-token"))
                .willReturn(createUserInfo("ssafy@ssafy.com", "김싸피"));

        authService.googleLogin(createRequest("google-authorization-code"), googleSession);

        NaverLoginRequest request = createNaverRequest("naver-authorization-code");
        MockHttpSession naverSession = new MockHttpSession();

        given(naverOAuthClient.getUserAccessToken("naver-authorization-code", STATE))
                .willReturn(createNaverToken("naver-access-token"));
        given(naverOAuthClient.getUserInfo("naver-access-token"))
                .willReturn(createNaverUserInfo("ssafy@ssafy.com", "김싸피"));

        // when
        NaverLoginResponse response = authService.naverLogin(request, naverSession);

        // then
        assertThat(response)
                .extracting("name", "email", "imageUrl")
                .contains("김싸피", "ssafy@ssafy.com", "");

        entityManager.flush();
        entityManager.clear();

        List<Member> members = memberRepository.findAll();
        assertThat(members).hasSize(1)
                .extracting("email", "name")
                .containsExactlyInAnyOrder(
                        tuple("ssafy@ssafy.com", "김싸피")
                );
        assertThat(naverSession.getAttribute("loginMember"))
                .extracting("id", "name", "email")
                .containsExactly(members.get(0).getId(), "김싸피", "ssafy@ssafy.com");
    }

    @DisplayName("네이버 프로필에 이메일이 없으면 예외가 발생하고 회원이 저장되지 않는다.")
    @Test
    void naverLoginWithoutEmail() {
        // given
        NaverLoginRequest request = createNaverRequest("authorization-code");
        MockHttpSession session = new MockHttpSession();

        given(naverOAuthClient.getUserAccessToken("authorization-code", STATE))
                .willReturn(createNaverToken("naver-access-token"));
        given(naverOAuthClient.getUserInfo("naver-access-token"))
                .willReturn(createNaverUserInfo(null, "김싸피"));

        // when // then
        assertThatThrownBy(() -> authService.naverLogin(request, session))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(AuthErrorCode.NAVER_EMAIL_REQUIRED);

        assertThat(memberRepository.findAll()).isEmpty();
        assertThat(session.getAttribute("loginMember")).isNull();
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

    private NaverLoginRequest createNaverRequest(String code) {
        return NaverLoginRequest.builder()
                .code(code)
                .state(STATE)
                .build();
    }

    private NaverTokenResponse createNaverToken(String accessToken) {
        return NaverTokenResponse.builder()
                .accessToken(accessToken)
                .build();
    }

    private NaverUserInfoResponse createNaverUserInfo(String email, String name) {
        return NaverUserInfoResponse.builder()
                .resultCode("00")
                .message("success")
                .profile(NaverUserInfoResponse.NaverProfile.builder()
                        .id("naver-id")
                        .email(email)
                        .name(name)
                        .nickname("싸피")
                        .profileImage("https://ssl.pstatic.net/profile.png")
                        .build())
                .build();
    }

    private Member createMember(String email, String name) {
        return Member.builder()
                .email(email)
                .name(name)
                .build();
    }

}
