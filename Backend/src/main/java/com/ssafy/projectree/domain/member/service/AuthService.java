package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.controller.request.GoogleLoginRequest;
import com.ssafy.projectree.domain.member.controller.response.GoogleLoginResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleTokenResponse;
import com.ssafy.projectree.domain.member.controller.response.session.GoogleUserInfoResponse;
import jakarta.servlet.http.HttpSession;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class AuthService {


    private final GoogleOAuthClient googleOAuthClient;
    private final MemberRepository memberRepository;

    @Transactional
    public GoogleLoginResponse googleLogin(GoogleLoginRequest request, HttpSession session) {
        GoogleUserInfoResponse userInfo = fetchUserInfo(request);
        Member member = findByEmailOrSave(userInfo);

        session.setAttribute(SESSION_LOGIN_MEMBER, LoginMember.from(member));
        return GoogleLoginResponse.from(member);
    }

    private GoogleUserInfoResponse fetchUserInfo(GoogleLoginRequest request) {
        GoogleTokenResponse token = googleOAuthClient.getUserAccessToken(
                request.getCode(),
                request.getRedirectUri()
        );
        return googleOAuthClient.getUserInfo(token.getAccessToken());
    }

    private Member findByEmailOrSave(GoogleUserInfoResponse userInfo) {
        return memberRepository.findByEmail(userInfo.getEmail())
                .orElseGet(() -> memberRepository.save(userInfo.toMember()));
    }
}
