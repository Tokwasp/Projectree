package com.ssafy.projectree.domain.notification.repository;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class EmitterRepositoryTest {

    private static final int MEMBER_ID = 7;
    private static final int OTHER_MEMBER_ID = 8;

    private final EmitterRepository emitterRepository = new EmitterRepository();

    @DisplayName("한 회원이 여러 탭을 열면 연결이 각각 보관된다.")
    @Test
    void findAllByMemberId() {
        // given
        SseEmitter firstTab = emitterRepository.save(MEMBER_ID, new SseEmitter());
        SseEmitter secondTab = emitterRepository.save(MEMBER_ID, new SseEmitter());

        // when
        List<SseEmitter> emitters = emitterRepository.findAllByMemberId(MEMBER_ID);

        // then
        assertThat(emitters).containsExactly(firstTab, secondTab);
    }

    @DisplayName("회원 id 를 키로 쓰므로 다른 회원의 연결은 섞이지 않는다.")
    @Test
    void findAllByMemberIdDoesNotMatchOtherMember() {
        // given
        SseEmitter target = emitterRepository.save(MEMBER_ID, new SseEmitter());
        emitterRepository.save(OTHER_MEMBER_ID, new SseEmitter());

        // when
        List<SseEmitter> emitters = emitterRepository.findAllByMemberId(MEMBER_ID);

        // then
        assertThat(emitters).containsExactly(target);
    }

    @DisplayName("접속 중인 연결이 없는 회원을 조회하면 빈 결과를 반환한다.")
    @Test
    void findAllByMemberIdWhenNotSubscribed() {
        // given
        emitterRepository.save(MEMBER_ID, new SseEmitter());

        // when
        List<SseEmitter> emitters = emitterRepository.findAllByMemberId(OTHER_MEMBER_ID);

        // then
        assertThat(emitters).isEmpty();
    }

    @DisplayName("탭을 하나 닫으면 끊긴 연결만 빠지고 나머지 탭은 남는다.")
    @Test
    void delete() {
        // given
        SseEmitter closed = emitterRepository.save(MEMBER_ID, new SseEmitter());
        SseEmitter alive = emitterRepository.save(MEMBER_ID, new SseEmitter());

        // when
        emitterRepository.delete(MEMBER_ID, closed);

        // then
        assertThat(emitterRepository.findAllByMemberId(MEMBER_ID)).containsExactly(alive);
    }

    @DisplayName("마지막 연결이 빠지면 빈 목록이 쌓이지 않도록 회원 자체가 제거된다.")
    @Test
    void deleteRemovesMemberWhenLastEmitterLeft() {
        // given
        SseEmitter onlyTab = emitterRepository.save(MEMBER_ID, new SseEmitter());

        // when
        emitterRepository.delete(MEMBER_ID, onlyTab);

        // then
        assertThat(emitterRepository.findAll()).doesNotContainKey(MEMBER_ID);
        assertThat(emitterRepository.findAllByMemberId(MEMBER_ID)).isEmpty();
    }

    @DisplayName("접속 중이 아닌 회원의 연결을 지워도 예외가 나지 않는다.")
    @Test
    void deleteWhenNotSubscribed() {
        // when
        emitterRepository.delete(MEMBER_ID, new SseEmitter());

        // then
        assertThat(emitterRepository.findAll()).isEmpty();
    }

    @DisplayName("하트비트를 위해 회원과 무관하게 모든 연결을 조회한다.")
    @Test
    void findAll() {
        // given
        emitterRepository.save(MEMBER_ID, new SseEmitter());
        emitterRepository.save(MEMBER_ID, new SseEmitter());
        emitterRepository.save(OTHER_MEMBER_ID, new SseEmitter());

        // when
        Map<Integer, List<SseEmitter>> emitters = emitterRepository.findAll();

        // then
        assertThat(emitters).hasSize(2);
        assertThat(emitters.get(MEMBER_ID)).hasSize(2);
        assertThat(emitters.get(OTHER_MEMBER_ID)).hasSize(1);
    }

    @DisplayName("전체 조회 결과를 순회하는 동안 원본에서 연결이 삭제되어도 순회에 영향을 주지 않는다.")
    @Test
    void findAllReturnsCopy() {
        // given
        SseEmitter emitter = emitterRepository.save(MEMBER_ID, new SseEmitter());
        Map<Integer, List<SseEmitter>> emitters = emitterRepository.findAll();

        // when
        emitterRepository.delete(MEMBER_ID, emitter);

        // then
        assertThat(emitters).containsKey(MEMBER_ID);
        assertThat(emitterRepository.findAll()).isEmpty();
    }

    @DisplayName("회원별 조회 결과를 순회하는 동안 원본에서 연결이 삭제되어도 순회에 영향을 주지 않는다.")
    @Test
    void findAllByMemberIdReturnsCopy() {
        // given
        SseEmitter emitter = emitterRepository.save(MEMBER_ID, new SseEmitter());
        List<SseEmitter> emitters = emitterRepository.findAllByMemberId(MEMBER_ID);

        // when
        emitterRepository.delete(MEMBER_ID, emitter);

        // then
        assertThat(emitters).hasSize(1);
        assertThat(emitterRepository.findAllByMemberId(MEMBER_ID)).isEmpty();
    }
}
