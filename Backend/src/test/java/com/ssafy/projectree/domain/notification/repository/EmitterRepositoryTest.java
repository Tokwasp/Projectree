package com.ssafy.projectree.domain.notification.repository;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class EmitterRepositoryTest {

    private final EmitterRepository emitterRepository = new EmitterRepository();

    @DisplayName("한 회원이 여러 탭을 열면 연결이 각각 보관된다.")
    @Test
    void findAllByMemberId() {
        // given
        SseEmitter firstTab = emitterRepository.save("7_1000", new SseEmitter());
        SseEmitter secondTab = emitterRepository.save("7_2000", new SseEmitter());

        // when
        Map<String, SseEmitter> emitters = emitterRepository.findAllByMemberId(7);

        // then
        assertThat(emitters).hasSize(2)
                .containsEntry("7_1000", firstTab)
                .containsEntry("7_2000", secondTab);
    }

    @DisplayName("회원 id 뒤에 구분자를 붙여 스캔하므로 id가 앞부분만 겹치는 다른 회원의 연결은 걸리지 않는다.")
    @Test
    void findAllByMemberIdDoesNotMatchOtherMemberWithSamePrefix() {
        // given
        SseEmitter target = emitterRepository.save("1_1000", new SseEmitter());
        emitterRepository.save("11_1000", new SseEmitter());
        emitterRepository.save("123_1000", new SseEmitter());

        // when
        Map<String, SseEmitter> emitters = emitterRepository.findAllByMemberId(1);

        // then
        assertThat(emitters).hasSize(1)
                .containsEntry("1_1000", target);
    }

    @DisplayName("접속 중인 연결이 없는 회원을 조회하면 빈 결과를 반환한다.")
    @Test
    void findAllByMemberIdWhenNotSubscribed() {
        // given
        emitterRepository.save("7_1000", new SseEmitter());

        // when
        Map<String, SseEmitter> emitters = emitterRepository.findAllByMemberId(8);

        // then
        assertThat(emitters).isEmpty();
    }

    @DisplayName("연결을 삭제하면 더 이상 조회되지 않는다.")
    @Test
    void deleteById() {
        // given
        emitterRepository.save("7_1000", new SseEmitter());
        emitterRepository.save("7_2000", new SseEmitter());

        // when
        emitterRepository.deleteById("7_1000");

        // then
        assertThat(emitterRepository.findAllByMemberId(7)).hasSize(1)
                .containsKey("7_2000");
    }

    @DisplayName("하트비트를 위해 회원과 무관하게 모든 연결을 조회한다.")
    @Test
    void findAll() {
        // given
        emitterRepository.save("7_1000", new SseEmitter());
        emitterRepository.save("8_1000", new SseEmitter());

        // when
        Map<String, SseEmitter> emitters = emitterRepository.findAll();

        // then
        assertThat(emitters).hasSize(2)
                .containsKeys("7_1000", "8_1000");
    }

    @DisplayName("전체 조회 결과를 순회하는 동안 원본에서 연결이 삭제되어도 순회에 영향을 주지 않는다.")
    @Test
    void findAllReturnsCopy() {
        // given
        emitterRepository.save("7_1000", new SseEmitter());
        Map<String, SseEmitter> emitters = emitterRepository.findAll();

        // when
        emitterRepository.deleteById("7_1000");

        // then
        assertThat(emitters).hasSize(1);
        assertThat(emitterRepository.findAll()).isEmpty();
    }

    @DisplayName("회원별 조회 결과를 순회하는 동안 원본에서 연결이 삭제되어도 순회에 영향을 주지 않는다.")
    @Test
    void findAllByMemberIdReturnsCopy() {
        // given
        emitterRepository.save("7_1000", new SseEmitter());
        Map<String, SseEmitter> emitters = emitterRepository.findAllByMemberId(7);

        // when
        emitterRepository.deleteById("7_1000");

        // then
        assertThat(emitters).hasSize(1);
        assertThat(emitterRepository.findAllByMemberId(7)).isEmpty();
    }
}
