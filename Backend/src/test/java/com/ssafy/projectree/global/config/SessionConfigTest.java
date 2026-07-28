package com.ssafy.projectree.global.config;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.config.session.SessionConfig;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.RedisSerializer;

import java.nio.charset.StandardCharsets;

import static org.assertj.core.api.Assertions.assertThat;

class SessionConfigTest {

    private final RedisSerializer<Object> serializer =
            new SessionConfig(false, "Lax").springSessionDefaultRedisSerializer();

    @DisplayName("세션 값은 Redis 콘솔에서 그대로 읽을 수 있는 JSON으로 저장된다.")
    @Test
    void serializeToReadableJson() {
        // given
        Long memberId = 1L;

        // when
        byte[] serialized = serializer.serialize(memberId);

        // then
        assertThat(new String(serialized, StandardCharsets.UTF_8)).isEqualTo("1");
    }

    @DisplayName("Long은 final 타입이라 타입 정보가 붙지 않으므로 Number로 꺼내야 한다.")
    @Test
    void deserializeNumberAsNumber() {
        // given
        Long memberId = 1L;
        byte[] serialized = serializer.serialize(memberId);

        // when
        Object deserialized = serializer.deserialize(serialized);

        // then
        assertThat(deserialized).isInstanceOf(Number.class);
        assertThat(((Number) deserialized).longValue()).isEqualTo(memberId);
    }

    @DisplayName("LoginMember는 타입 정보(@class)와 함께 저장된다.")
    @Test
    void serializeLoginMemberWithTypeInfo() {
        // given
        LoginMember loginMember = createLoginMember();

        // when
        byte[] serialized = serializer.serialize(loginMember);

        // then
        assertThat(new String(serialized, StandardCharsets.UTF_8))
                .contains("\"@class\":\"com.ssafy.projectree.domain.member.LoginMember\"");
    }

    @DisplayName("LoginMember는 타입 정보 덕분에 원래 타입 그대로 복원되고, 식별자도 Long으로 돌아온다.")
    @Test
    void deserializeLoginMember() {
        // given
        LoginMember loginMember = createLoginMember();
        byte[] serialized = serializer.serialize(loginMember);

        // when
        Object deserialized = serializer.deserialize(serialized);

        // then
        assertThat(deserialized).isInstanceOf(LoginMember.class)
                .extracting("id", "name", "email")
                .containsExactly(1L, "김싸피", "ssafy@gmail.com");
    }

    private LoginMember createLoginMember() {
        return LoginMember.builder()
                .id(1L)
                .name("김싸피")
                .email("ssafy@gmail.com")
                .build();
    }
}
