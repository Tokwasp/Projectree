package com.ssafy.projectree.domain.member.repository;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class MemberRepositoryTest extends IntegrationTestSupport {

    @Autowired
    private MemberRepository memberRepository;

    @DisplayName("이메일로 회원을 조회한다.")
    @Test
    void findByEmail() {
        // given
        Member member1 = createMember("ssafy@gmail.com", "김싸피");
        Member member2 = createMember("other@gmail.com", "이싸피");
        memberRepository.saveAll(List.of(member1, member2));

        // when
        Optional<Member> found = memberRepository.findByEmail("ssafy@gmail.com");

        // then
        assertThat(found).isPresent()
                .get()
                .extracting("email", "name")
                .containsExactly("ssafy@gmail.com", "김싸피");
    }

    private Member createMember(String email, String name) {
        return Member.builder()
                .email(email)
                .name(name)
                .build();
    }

}
