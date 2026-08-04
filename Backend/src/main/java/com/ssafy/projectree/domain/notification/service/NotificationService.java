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

import java.util.Optional;
import java.util.concurrent.atomic.AtomicLong;

import static com.ssafy.projectree.domain.notification.repository.EmitterRepository.EMITTER_ID_DELIMITER;

@Service
@RequiredArgsConstructor
@Transactional(readOnly = true)
public class NotificationService {

    private static final String CONNECT_MESSAGE = "연결되었습니다.";

    private final NotificationRepository notificationRepository;
    private final MemberRepository memberRepository;
    private final EmitterRepository emitterRepository;
    private final NotificationSender notificationSender;
    private final NotificationPublisher notificationPublisher;
    private final NotificationProperties notificationProperties;

    /**
     * 밀리초만으로 키를 만들면 같은 밀리초에 들어온 두 구독이 서로를 덮어써
     * 먼저 붙은 탭이 "연결은 살아 있는데 알림만 오지 않는" 상태가 된다.
     * 연결마다 고유한 값이 필요하므로 시퀀스를 함께 붙인다.
     */
    private final AtomicLong emitterSequence = new AtomicLong();

    public SseEmitter subscribe(int memberId, String lastEventId) {
        String emitterId = createEmitterId(memberId);
        SseEmitter emitter = emitterRepository.save(emitterId, createEmitter());

        registerLifecycleCallbacks(emitterId, emitter);

        notificationSender.send(emitterId, emitter, emitterId,
                NotificationSender.CONNECT_EVENT, CONNECT_MESSAGE);

        resendMissed(memberId, emitterId, emitter, lastEventId);

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
        return memberId + EMITTER_ID_DELIMITER
                + System.currentTimeMillis() + EMITTER_ID_DELIMITER
                + emitterSequence.incrementAndGet();
    }

    private SseEmitter createEmitter() {
        return new SseEmitter(notificationProperties.getSse().getTimeout().toMillis());
    }

    /**
     * onTimeout/onError 에서 직접 지우지 않고 complete() 만 호출한다.
     * 삭제 지점을 onCompletion 하나로 모아 두면 지우는 코드가 한 곳뿐이라 빠뜨릴 일이 없다.
     */
    private void registerLifecycleCallbacks(String emitterId, SseEmitter emitter) {
        emitter.onCompletion(() -> emitterRepository.deleteById(emitterId));
        emitter.onTimeout(emitter::complete);
        emitter.onError(throwable -> emitter.complete());
    }

    private void resendMissed(int memberId, String emitterId, SseEmitter emitter, String lastEventId) {
        parseEventId(lastEventId).ifPresent(eventId ->
                notificationRepository
                        .findNotReceivedMessages(memberId, eventId)
                        .forEach(notification -> notificationSender.send(
                                emitterId,
                                emitter,
                                String.valueOf(notification.getId()),
                                NotificationSender.NOTIFICATION_EVENT,
                                NotificationMessage.from(notification))));
    }

    /**
     * 더미 이벤트의 id를 받은 경우처럼 숫자가 아니면 재전송만 건너뛴다.
     * 파싱 실패로 구독 자체가 깨지면 안 된다.
     */
    private Optional<Integer> parseEventId(String lastEventId) {
        if (lastEventId.isEmpty()) {
            return Optional.empty();
        }
        try {
            return Optional.of(Integer.parseInt(lastEventId));
        } catch (NumberFormatException e) {
            return Optional.empty();
        }
    }

    private void validateReceiverExists(int receiverId) {
        if (!memberRepository.existsById(receiverId)) {
            throw new CustomException(CommonErrorCode.MEMBER_NOT_FOUND);
        }
    }
}
