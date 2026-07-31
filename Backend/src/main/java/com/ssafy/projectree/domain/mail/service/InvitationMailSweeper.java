package com.ssafy.projectree.domain.mail.service;

import com.ssafy.projectree.domain.mail.entity.InvitationMail;
import com.ssafy.projectree.domain.mail.entity.MailSendStatus;
import com.ssafy.projectree.domain.mail.repository.InvitationMailRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.domain.PageRequest;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import java.time.Duration;
import java.time.LocalDateTime;

@Slf4j
@Component
@RequiredArgsConstructor
public class InvitationMailSweeper {

    private static final int BATCH_SIZE = 20;
    private static final Duration STALE_CLAIM_CUTOFF = Duration.ofMinutes(5);

    private final InvitationMailSendProcessor processor;
    private final InvitationMailRepository invitationMailRepository;
    private final InvitationMailClient mailClient;

    @Scheduled(fixedDelay = 30_000)
    public void sweep() {
        LocalDateTime now = LocalDateTime.now();
        int recoveredCount = processor.recoverInterruptedSends(now.minus(STALE_CLAIM_CUTOFF));
        if (recoveredCount > 0) {
            log.warn("중단된 초대 메일 발송 {}건을 복구했습니다.", recoveredCount);
        }

        invitationMailRepository
                .findAllBySendStatusOrderByIdAsc(MailSendStatus.NOT_REQUESTED, PageRequest.of(0, BATCH_SIZE))
                .forEach(mail -> processMail(mail, now));
    }

    private void processMail(InvitationMail mail, LocalDateTime now) {
        try {
            processor.claim(mail.getId(), now).ifPresent(this::send);
        } catch (Exception e) {
            log.error("초대 메일 처리 중 예상치 못한 오류가 발생했습니다. mailId={}", mail.getId(), e);
        }
    }

    private void send(InvitationMailContent content) {
        try {
            mailClient.send(content);
            processor.recordSuccess(content.mailId());
        } catch (Exception e) {
            log.warn("초대 메일 발송에 실패했습니다. mailId={}", content.mailId(), e);
            try {
                processor.recordFailure(content.mailId(), failureReason(e));
            } catch (Exception failureRecordingException) {
                // 실패 기록까지 실패하면 REQUESTING 상태로 남고 다음 스위프의 복구 단계가 처리한다.
                log.error("초대 메일 발송 실패를 기록하지 못했습니다. mailId={}", content.mailId(), failureRecordingException);
            }
        }
    }

    private String failureReason(Exception e) {
        return e.getMessage() != null ? e.getMessage() : e.getClass().getSimpleName();
    }
}
