package com.ssafy.projectree.domain.member.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.controller.response.MemberSearchResponse;
import com.ssafy.projectree.domain.member.controller.response.MemberProfileResponse;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
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

    @PersistenceContext
    private EntityManager entityManager;

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

    @DisplayName("회원 식별자로 프로필을 조회한다.")
    @Test
    void findProfile() {
        Member member = memberRepository.save(createMember("owner@example.com", "프로필 주인"));

        MemberProfileResponse response = memberService.findProfile(member.getId());

        assertThat(response)
                .extracting("memberId", "name", "email")
                .containsExactly(member.getId(), "프로필 주인", "owner@example.com");
    }

    @DisplayName("존재하지 않는 회원 식별자로 프로필을 조회하면 MEMBER_NOT_FOUND 예외가 발생한다.")
    @Test
    void findProfile_notFound_throwsException() {
        assertThatThrownBy(() -> memberService.findProfile(0))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(CommonErrorCode.MEMBER_NOT_FOUND);
    }

    @DisplayName("프로필 이미지를 등록하지 않은 회원은 이미지 URL을 null로 조회한다.")
    @Test
    void findProfile_withoutUploadFile_returnsNullImageUrl() {
        Member member = memberRepository.save(createMember("owner@example.com", "프로필 주인"));

        MemberProfileResponse response = memberService.findProfile(member.getId());

        assertThat(response.getProfileImageUrl()).isNull();
    }

    @DisplayName("회원을 탈퇴시키면 행이 남은 채로 삭제 상태로 전환된다.")
    @Test
    void deleteMember() {
        // given
        Member member = memberRepository.save(createMember("quit@example.com", "탈퇴 예정"));

        // when
        memberService.deleteMember(member.getId());

        // then
        entityManager.flush();
        entityManager.clear();

        Member found = memberRepository.findById(member.getId()).orElseThrow();
        assertThat(found.isDeleted()).isTrue();
    }

    @DisplayName("존재하지 않는 회원 식별자로 탈퇴하면 MEMBER_NOT_FOUND 예외가 발생한다.")
    @Test
    void deleteMember_notFound_throwsException() {
        // when & then
        assertThatThrownBy(() -> memberService.deleteMember(0))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(CommonErrorCode.MEMBER_NOT_FOUND);
    }

    /**
     * 탈퇴 시 세션을 무효화하지 않으므로 남아 있는 세션으로 탈퇴를 다시 호출할 수 있다.
     * 두 번째 호출도 삭제 상태를 유지하며 실패하지 않아야 한다.
     */
    @DisplayName("이미 탈퇴한 회원을 다시 탈퇴시켜도 삭제 상태를 유지한다.")
    @Test
    void deleteMember_whenAlreadyDeleted_staysDeleted() {
        // given
        Member member = memberRepository.save(createMember("quit@example.com", "탈퇴 예정"));
        memberService.deleteMember(member.getId());

        entityManager.flush();
        entityManager.clear();

        // when
        memberService.deleteMember(member.getId());

        // then
        entityManager.flush();
        entityManager.clear();

        Member found = memberRepository.findById(member.getId()).orElseThrow();
        assertThat(found.isDeleted()).isTrue();
    }

    private Member createMember(String email, String name) {
        return Member.builder()
                .email(email)
                .name(name)
                .build();
    }
}
