package com.ssafy.projectree.domain.project.service;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class InvitationTokenGeneratorTest {

    private final InvitationTokenGenerator invitationTokenGenerator = new InvitationTokenGenerator();

    @DisplayName("초대 토큰은 URL-safe 문자열이고 해시는 64자리 hex 문자열이다.")
    @Test
    void generate() {
        // when
        InvitationToken token = invitationTokenGenerator.generate();

        // then
        assertThat(token.rawToken()).matches("[A-Za-z0-9_-]+");
        assertThat(token.rawToken()).hasSize(43);
        assertThat(token.rawToken()).doesNotContain("+", "/", "=");
        assertThat(token.tokenHash()).matches("[0-9a-f]{64}");
    }

    @DisplayName("같은 원문 토큰은 같은 해시를 반환하고 새로 발급한 토큰은 서로 다르다.")
    @Test
    void hash_isDeterministicAndTokensAreDifferent() {
        // given
        InvitationToken first = invitationTokenGenerator.generate();
        InvitationToken second = invitationTokenGenerator.generate();

        // when
        String hashedAgain = invitationTokenGenerator.hash(first.rawToken());

        // then
        assertThat(hashedAgain).isEqualTo(first.tokenHash());
        assertThat(second.rawToken()).isNotEqualTo(first.rawToken());
    }
}
