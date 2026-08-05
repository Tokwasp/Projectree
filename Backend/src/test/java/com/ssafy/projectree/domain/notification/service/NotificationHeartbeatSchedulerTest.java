package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.times;

@ExtendWith(MockitoExtension.class)
class NotificationHeartbeatSchedulerTest {

    private static final int MEMBER_ID = 7;
    private static final int OTHER_MEMBER_ID = 8;

    @InjectMocks
    private NotificationHeartbeatScheduler notificationHeartbeatScheduler;

    @Mock
    private EmitterRepository emitterRepository;

    @Mock
    private NotificationSender notificationSender;

    @DisplayName("알림이 뜸한 시간에도 열린 모든 연결에 하트비트를 흘려보낸다.")
    @Test
    void sendHeartbeat() {
        // given
        given(emitterRepository.findAll()).willReturn(Map.of(
                MEMBER_ID, List.of(new SseEmitter()),
                OTHER_MEMBER_ID, List.of(new SseEmitter())
        ));

        // when
        notificationHeartbeatScheduler.sendHeartbeat();

        // then
        then(notificationSender).should().sendHeartbeat(eq(MEMBER_ID), any(SseEmitter.class));
        then(notificationSender).should().sendHeartbeat(eq(OTHER_MEMBER_ID), any(SseEmitter.class));
    }

    @DisplayName("한 회원이 탭을 여러 개 열어 두었으면 연결마다 하트비트가 나간다.")
    @Test
    void sendHeartbeatToEveryTabOfSameMember() {
        // given
        given(emitterRepository.findAll()).willReturn(Map.of(
                MEMBER_ID, List.of(new SseEmitter(), new SseEmitter())
        ));

        // when
        notificationHeartbeatScheduler.sendHeartbeat();

        // then
        then(notificationSender).should(times(2))
                .sendHeartbeat(eq(MEMBER_ID), any(SseEmitter.class));
    }

    @DisplayName("열린 연결이 하나도 없으면 하트비트를 보내지 않는다.")
    @Test
    void sendHeartbeatWhenNoEmitter() {
        // given
        given(emitterRepository.findAll()).willReturn(Map.of());

        // when
        notificationHeartbeatScheduler.sendHeartbeat();

        // then
        then(notificationSender).shouldHaveNoInteractions();
    }
}
