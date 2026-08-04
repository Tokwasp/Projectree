package com.ssafy.projectree.domain.notification.service;

import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.notification.controller.request.NotificationCallbackRequest;
import com.ssafy.projectree.domain.notification.dto.NotificationMessage;
import com.ssafy.projectree.domain.notification.entity.Notification;
import com.ssafy.projectree.domain.notification.repository.EmitterRepository;
import com.ssafy.projectree.domain.notification.repository.NotificationRepository;
import com.ssafy.projectree.global.config.notification.NotificationProperties;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class NotificationService {

    private final NotificationRepository notificationRepository;
    private final MemberRepository memberRepository;
    private final EmitterRepository emitterRepository;
    private final NotificationSender notificationSender;
    private final NotificationPublisher notificationPublisher;
    private final NotificationProperties notificationProperties;

    public SseEmitter subscribe(int memberId, Integer lastEventId) {
        String emitterId = createEmitterId(memberId);
        SseEmitter emitter = emitterRepository.save(emitterId, createEmitter());

        emitter.onCompletion(() -> emitterRepository.deleteById(emitterId));
        emitter.onTimeout(emitter::complete);
        emitter.onError(throwable -> emitter.complete());

        notificationSender.sendSubscriptionMessage(emitterId, emitter, "connect", "연결되었습니다.");
        if (isValidLastEventId(lastEventId)) {
            notificationRepository.findNotReceivedMessages(memberId, lastEventId)
                    .forEach(notification -> notificationSender.send(
                            emitterId,
                            emitter,
                            String.valueOf(notification.getId()),
                            NotificationSender.NOTIFICATION_EVENT,
                            NotificationMessage.from(notification))
                    );
        }
        return emitter;
    }

    /**
     * 저장이 먼저이고 발행이 나중이다. 순서를 바꾸면 아직 id가 없어서 SSE 이벤트 id를 만들 수 없고,
     * Last-Event-ID 복구의 기준이 사라진다.
     * <p>
     * 수신자가 접속 중이 아니어도 정상이다. 알림은 DB에 남았고 다음 구독 때 받아 갈 수 있다.
     */
    @Transactional
    public void handleCallback(NotificationCallbackRequest request) {
        validateReceiverExists(request.getReceiverId());

        Notification notification = notificationRepository.save(request.toEntity());

        notificationPublisher.publish(NotificationMessage.from(notification));
    }

    private String createEmitterId(int memberId) {
        return memberId + "_" + System.currentTimeMillis();
    }

    private SseEmitter createEmitter() {
        return new SseEmitter(notificationProperties.getSse().getTimeout().toMillis());
    }

    private boolean isValidLastEventId(Integer lastEventId) {
        return lastEventId != null && lastEventId > 0;
    }

    private void validateReceiverExists(int receiverId) {
        if (!memberRepository.existsById(receiverId)) {
            throw new CustomException(CommonErrorCode.MEMBER_NOT_FOUND);
        }
    }
}
