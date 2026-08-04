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
        SseEmitter emitter = emitterRepository.save(memberId, createEmitter());

        emitter.onCompletion(() -> emitterRepository.delete(memberId, emitter));
        emitter.onTimeout(emitter::complete);
        emitter.onError(throwable -> emitter.complete());

        notificationSender.sendSubscriptionMessage(memberId, emitter, "connect", "연결되었습니다.");
        if (isValidLastEventId(lastEventId)) {
            notificationRepository.findNotReceivedMessages(memberId, lastEventId)
                    .forEach(notification -> notificationSender.send(
                            memberId,
                            emitter,
                            String.valueOf(notification.getId()),
                            NotificationSender.NOTIFICATION_EVENT,
                            NotificationMessage.from(notification))
                    );
        }
        return emitter;
    }

    @Transactional
    public void handleCallback(NotificationCallbackRequest request) {
        if (notExistMemberBy(request.getReceiverId())) {
            throw new CustomException(CommonErrorCode.MEMBER_NOT_FOUND);
        }

        Notification notification = notificationRepository.save(request.toEntity());
        notificationPublisher.publish(NotificationMessage.from(notification));
    }

    private SseEmitter createEmitter() {
        return new SseEmitter(notificationProperties.getSse().getTimeout().toMillis());
    }

    private boolean isValidLastEventId(Integer lastEventId) {
        return lastEventId != null && lastEventId > 0;
    }

    private boolean notExistMemberBy(int request) {
        return !memberRepository.existsById(request);
    }

}
