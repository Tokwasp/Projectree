package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.controller.request.GoogleLoginRequest;
import com.ssafy.projectree.domain.member.controller.request.NaverLoginRequest;
import com.ssafy.projectree.domain.member.controller.response.GoogleLoginResponse;
import com.ssafy.projectree.domain.member.controller.response.NaverLoginResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleTokenResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleUserInfoResponse;
import com.ssafy.projectree.domain.member.controller.response.session.NaverTokenResponse;
import com.ssafy.projectree.domain.member.controller.response.session.NaverUserInfoResponse;
import com.ssafy.projectree.global.exception.ErrorCode;
import jakarta.servlet.http.HttpSession;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AuthService {

    private static final String SESSION_LOGIN_MEMBER = "loginMember";

    private final GoogleOAuthClient googleOAuthClient;
    private final NaverOAuthClient naverOAuthClient;
    private final MemberRepository memberRepository;

    @Transactional
    public GoogleLoginResponse googleLogin(GoogleLoginRequest request, HttpSession session) {
        GoogleUserInfoResponse userInfo = fetchUserInfo(request);
        Member member = findByEmailOrSave(userInfo);

        session.setAttribute(SESSION_LOGIN_MEMBER, LoginMember.from(member));
        return GoogleLoginResponse.from(member);
    }

    @Transactional
    public NaverLoginResponse naverLogin(NaverLoginRequest request, HttpSession session) {
        NaverUserInfoResponse userInfo = fetchUserInfo(request);
        Member member = findByEmailOrSave(userInfo);

        session.setAttribute(SESSION_LOGIN_MEMBER, LoginMember.from(member));
        return NaverLoginResponse.from(member);
    }

    private GoogleUserInfoResponse fetchUserInfo(GoogleLoginRequest request) {
        GoogleTokenResponse token = googleOAuthClient.getUserAccessToken(
                request.getCode(),
                request.getRedirectUri()
        );
        return googleOAuthClient.getUserInfo(token.getAccessToken());
    }

    private NaverUserInfoResponse fetchUserInfo(NaverLoginRequest request) {
        NaverTokenResponse token = naverOAuthClient.getUserAccessToken(
                request.getCode(),
                request.getState()
        );
        return naverOAuthClient.getUserInfo(token.getAccessToken());
    }

    private Member findByEmailOrSave(GoogleUserInfoResponse userInfo) {
        return memberRepository.findByEmail(userInfo.getEmail())
                .orElseGet(() -> memberRepository.save(userInfo.toMember()));
    }

    private Member findByEmailOrSave(NaverUserInfoResponse userInfo) {
        if (userInfo.hasNoEmail()) {
            throw new IllegalArgumentException(ErrorCode.NAVER_EMAIL_REQUIRED.getMessage());
        }
        return memberRepository.findByEmail(userInfo.getEmail())
                .orElseGet(() -> memberRepository.save(userInfo.toMember()));
    }
}
