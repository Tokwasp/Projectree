package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.controller.response.MemberSearchResponse;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MemberServiceTest extends IntegrationTestSupport {

    @Autowired
    private MemberService memberService;

    @Autowired
    private MemberRepository memberRepository;

    @DisplayName("이메일이 완전히 일치하는 회원을 조회한다.")
    @Test
    void findByEmail() {
        // given
        Member member = memberRepository.save(createMember("invitee@example.com", "초대 대상"));

        // when
        MemberSearchResponse response = memberService.findByEmail("invitee@example.com");

        // then
        assertThat(response)
                .extracting("memberId", "name", "email")
                .containsExactly(member.getId(), "초대 대상", "invitee@example.com");
    }

    @DisplayName("존재하지 않는 이메일을 조회하면 MEMBER_NOT_FOUND 예외가 발생한다.")
    @Test
    void findByEmail_notFound_throwsException() {
        // when & then
        assertThatThrownBy(() -> memberService.findByEmail("missing@example.com"))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(CommonErrorCode.MEMBER_NOT_FOUND);
    }

    private Member createMember(String email, String name) {
        return Member.builder()
                .email(email)
                .name(name)
                .build();
    }
}
