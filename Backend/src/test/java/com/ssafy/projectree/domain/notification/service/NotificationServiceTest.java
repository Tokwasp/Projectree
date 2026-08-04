package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.notification.controller.request.NotificationCallbackRequest;
import com.ssafy.projectree.domain.notification.dto.NotificationMessage;
import com.ssafy.projectree.domain.notification.entity.Notification;
import com.ssafy.projectree.domain.notification.entity.NotificationType;
import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import com.ssafy.projectree.domain.notification.repository.NotificationRepository;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.tuple;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.ArgumentCaptor.forClass;

class NotificationServiceTest extends IntegrationTestSupport {

    private static final int UNKNOWN_MEMBER_ID = 999_999;

    @Autowired
    private NotificationService notificationService;

    @Autowired
    private NotificationRepository notificationRepository;

    @Autowired
    private EmitterRepository emitterRepository;

    @Autowired
    private MemberRepository memberRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @MockitoBean
    private NotificationSender notificationSender;

    @MockitoBean
    private NotificationPublisher notificationPublisher;

    @AfterEach
    void clearEmitters() {
        emitterRepository.findAll().keySet().forEach(emitterRepository::deleteById);
    }

    @DisplayName("구독하면 연결이 회원 id로 찾을 수 있게 보관된다.")
    @Test
    void subscribe() {
        // given
        int memberId = saveMember().getId();

        // when
        SseEmitter emitter = notificationService.subscribe(memberId, "");

        // then
        Map<String, SseEmitter> emitters = emitterRepository.findAllByMemberId(memberId);
        assertThat(emitters).hasSize(1)
                .containsValue(emitter);
        assertThat(emitters.keySet()).allMatch(emitterId -> emitterId.startsWith(memberId + "_"));
    }

    @DisplayName("구독 직후 더미 이벤트를 보내 응답을 열어 둔다.")
    @Test
    void subscribeSendsConnectEvent() {
        // given
        int memberId = saveMember().getId();

        // when
        notificationService.subscribe(memberId, "");

        // then
        then(notificationSender).should().send(
                anyString(), any(SseEmitter.class), anyString(),
                eq("connect"), any());
    }

    @DisplayName("같은 회원이 탭을 두 개 열면 두 연결이 모두 남는다.")
    @Test
    void subscribeTwice() {
        // given
        int memberId = saveMember().getId();

        // when
        notificationService.subscribe(memberId, "");
        notificationService.subscribe(memberId, "");

        // then
        assertThat(emitterRepository.findAllByMemberId(memberId)).hasSize(2);
    }

    @DisplayName("첫 연결에는 Last-Event-ID 가 없으므로 지난 알림을 재전송하지 않는다.")
    @Test
    void subscribeWithoutLastEventId() {
        // given
        int memberId = saveMember().getId();
        saveNotification(memberId);

        // when
        notificationService.subscribe(memberId, "");

        // then
        then(notificationSender).should(never()).send(
                anyString(), any(SseEmitter.class), anyString(),
                eq(NotificationSender.NOTIFICATION_EVENT), any());
    }

    @DisplayName("재연결하면 마지막으로 받은 알림 이후의 알림만 다시 보낸다.")
    @Test
    void subscribeWithLastEventId() {
        // given
        int memberId = saveMember().getId();
        Notification received = saveNotification(memberId);
        Notification missed = saveNotification(memberId);

        // when
        notificationService.subscribe(memberId, String.valueOf(received.getId()));

        // then
        var eventIdCaptor = forClass(String.class);
        then(notificationSender).should(times(1)).send(
                anyString(), any(SseEmitter.class), eventIdCaptor.capture(),
                eq(NotificationSender.NOTIFICATION_EVENT), any());
        assertThat(eventIdCaptor.getValue()).isEqualTo(String.valueOf(missed.getId()));
    }

    @DisplayName("재전송하는 알림의 이벤트 id 는 알림 id 라서 다음 재연결의 기준이 된다.")
    @Test
    void subscribeWithLastEventIdSendsNotificationAsData() {
        // given
        int memberId = saveMember().getId();
        Notification received = saveNotification(memberId);
        Notification missed = saveNotification(memberId);

        // when
        notificationService.subscribe(memberId, String.valueOf(received.getId()));

        // then
        var messageCaptor = forClass(NotificationMessage.class);
        then(notificationSender).should().send(
                anyString(), any(SseEmitter.class), anyString(),
                eq(NotificationSender.NOTIFICATION_EVENT), messageCaptor.capture());
        assertThat(messageCaptor.getValue())
                .extracting(NotificationMessage::getNotificationId, NotificationMessage::getReceiverId)
                .containsExactly(missed.getId(), memberId);
    }

    @DisplayName("더미 이벤트의 id 처럼 숫자가 아닌 Last-Event-ID 가 오면 재전송만 건너뛰고 구독은 정상 처리한다.")
    @Test
    void subscribeWithNonNumericLastEventId() {
        // given
        int memberId = saveMember().getId();
        saveNotification(memberId);

        // when
        notificationService.subscribe(memberId, memberId + "_1754287263000");

        // then
        assertThat(emitterRepository.findAllByMemberId(memberId)).hasSize(1);
        then(notificationSender).should(never()).send(
                anyString(), any(SseEmitter.class), anyString(),
                eq(NotificationSender.NOTIFICATION_EVENT), any());
    }

    @DisplayName("콜백을 받으면 알림을 저장한다.")
    @Test
    void handleCallback() {
        // given
        int receiverId = saveMember().getId();

        // when
        notificationService.handleCallback(callbackRequest(NotificationType.TREE_CREATED, receiverId));

        // then
        entityManager.flush();
        entityManager.clear();
        List<Notification> notifications = notificationRepository.findAll();
        assertThat(notifications).hasSize(1)
                .extracting(Notification::getType, Notification::getReceiverId)
                .containsExactly(tuple(NotificationType.TREE_CREATED, receiverId));
    }

    @DisplayName("알림을 저장해 id를 얻은 뒤 그 id를 담아 발행한다.")
    @Test
    void handleCallbackPublishesSavedNotification() {
        // given
        int receiverId = saveMember().getId();

        // when
        notificationService.handleCallback(callbackRequest(NotificationType.MEETING_RECORD_CREATED, receiverId));

        // then
        var messageCaptor = forClass(NotificationMessage.class);
        then(notificationPublisher).should().publish(messageCaptor.capture());
        assertThat(messageCaptor.getValue())
                .extracting(
                        NotificationMessage::getType,
                        NotificationMessage::getReceiverId,
                        NotificationMessage::getMessage)
                .containsExactly(NotificationType.MEETING_RECORD_CREATED, receiverId,
                        NotificationType.MEETING_RECORD_CREATED.getMessage());
        assertThat(messageCaptor.getValue().getNotificationId()).isPositive();
    }

    @DisplayName("수신자가 접속 중이 아니어도 알림은 저장되고 발행된다.")
    @Test
    void handleCallbackWhenReceiverIsNotSubscribed() {
        // given
        int receiverId = saveMember().getId();

        // when
        notificationService.handleCallback(callbackRequest(NotificationType.TREE_CREATED, receiverId));

        // then
        entityManager.flush();
        entityManager.clear();
        assertThat(notificationRepository.findAll()).hasSize(1);
        then(notificationPublisher).should().publish(any(NotificationMessage.class));
    }

    @DisplayName("존재하지 않는 회원에게 보내는 콜백은 거절한다.")
    @Test
    void handleCallbackWithUnknownReceiver() {
        // when // then
        assertThatThrownBy(() -> notificationService.handleCallback(
                callbackRequest(NotificationType.TREE_CREATED, UNKNOWN_MEMBER_ID)))
                .isInstanceOf(CustomException.class)
                .hasMessage(CommonErrorCode.MEMBER_NOT_FOUND.getMessage());

        then(notificationPublisher).should(never()).publish(any(NotificationMessage.class));
    }

    private Member saveMember() {
        return memberRepository.saveAndFlush(Member.builder()
                .email("receiver@example.com")
                .name("수신자")
                .build());
    }

    private Notification saveNotification(int receiverId) {
        return notificationRepository.saveAndFlush(
                Notification.of(NotificationType.TREE_CREATED, receiverId));
    }

    private NotificationCallbackRequest callbackRequest(NotificationType type, int receiverId) {
        return NotificationCallbackRequest.builder()
                .type(type)
                .receiverId(receiverId)
                .build();
    }
}
