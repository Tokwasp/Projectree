package com.ssafy.projectree.domain.mail.entity;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class InvitationMailTest {

    private static final LocalDateTime REQUESTED_AT = LocalDateTime.of(2026, 7, 30, 10, 0);

    @DisplayName("메일 발송을 대기열에 넣으면 NOT_REQUESTED와 시도 횟수 0으로 생성된다.")
    @Test
    void queue_initializesMail() {
        // given & when
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");

        // then
        assertThat(mail.getInvitationId()).isEqualTo(1);
        assertThat(mail.getSendStatus()).isEqualTo(MailSendStatus.NOT_REQUESTED);
        assertThat(mail.getAttemptCount()).isZero();
        assertThat(mail.isTerminal()).isFalse();
    }

    @DisplayName("최대 시도 횟수 미만으로 발송에 실패하면 재시도 대기 상태가 된다.")
    @Test
    void fail_beforeMaximumAttempt_returnsToNotRequested() {
        // given
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");

        // when
        mail.beginAttempt(REQUESTED_AT);
        mail.fail("SMTP 연결에 실패했습니다.");

        // then
        assertThat(mail.getSendStatus()).isEqualTo(MailSendStatus.NOT_REQUESTED);
        assertThat(mail.getAttemptCount()).isEqualTo(1);
        assertThat(mail.getRequestedAt()).isEqualTo(REQUESTED_AT);
        assertThat(mail.getErrorMessage()).isEqualTo("SMTP 연결에 실패했습니다.");
        assertThat(mail.getInviteLink()).isNotNull();
    }

    @DisplayName("세 번째 발송 실패 시 FAILED로 확정되고 초대 링크는 제거된다.")
    @Test
    void fail_atMaximumAttempt_marksMailAsFailed() {
        // given
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");

        // when
        for (int attempt = 1; attempt <= 3; attempt++) {
            mail.beginAttempt(REQUESTED_AT.plusMinutes(attempt));
            mail.fail("SMTP 연결에 실패했습니다.");
        }

        // then
        assertThat(mail.getSendStatus()).isEqualTo(MailSendStatus.FAILED);
        assertThat(mail.getAttemptCount()).isEqualTo(3);
        assertThat(mail.getInviteLink()).isNull();
        assertThat(mail.isTerminal()).isTrue();
    }

    @DisplayName("발송에 성공하면 SENT로 변경되고 오류와 초대 링크가 제거된다.")
    @Test
    void succeed_marksMailAsSent() {
        // given
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");
        mail.beginAttempt(REQUESTED_AT);

        // when
        mail.succeed();

        // then
        assertThat(mail.getSendStatus()).isEqualTo(MailSendStatus.SENT);
        assertThat(mail.getErrorMessage()).isNull();
        assertThat(mail.getInviteLink()).isNull();
        assertThat(mail.isTerminal()).isTrue();
    }

    @DisplayName("발송 실패 사유는 500자를 초과하면 잘린다.")
    @Test
    void fail_truncatesLongErrorMessage() {
        // given
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");
        mail.beginAttempt(REQUESTED_AT);

        // when
        mail.fail("a".repeat(501));

        // then
        assertThat(mail.getErrorMessage()).hasSize(500);
    }

    @DisplayName("중단된 발송을 복구하면 시도 횟수는 유지한 채 재시도 대기 상태로 돌아간다.")
    @Test
    void recoverFromInterruptedSend_beforeMaximumAttempt_returnsToNotRequested() {
        // given
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");
        mail.beginAttempt(REQUESTED_AT);

        // when
        mail.recoverFromInterruptedSend();

        // then
        assertThat(mail.getSendStatus()).isEqualTo(MailSendStatus.NOT_REQUESTED);
        assertThat(mail.getAttemptCount()).isEqualTo(1);
        assertThat(mail.getErrorMessage()).isEqualTo("발송 도중 서버가 중단되었습니다.");
        assertThat(mail.getInviteLink()).isNotNull();
    }

    @DisplayName("마지막 발송 시도 중 중단된 메일을 복구하면 FAILED로 확정된다.")
    @Test
    void recoverFromInterruptedSend_atMaximumAttempt_marksMailAsFailed() {
        // given
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");
        for (int attempt = 1; attempt <= 2; attempt++) {
            mail.beginAttempt(REQUESTED_AT.plusMinutes(attempt));
            mail.fail("SMTP 연결에 실패했습니다.");
        }
        mail.beginAttempt(REQUESTED_AT.plusMinutes(3));

        // when
        mail.recoverFromInterruptedSend();

        // then
        assertThat(mail.getSendStatus()).isEqualTo(MailSendStatus.FAILED);
        assertThat(mail.getAttemptCount()).isEqualTo(3);
        assertThat(mail.getErrorMessage()).isEqualTo("발송 도중 서버가 중단되었습니다.");
        assertThat(mail.getInviteLink()).isNull();
    }

    @DisplayName("발송 중이 아닌 메일을 복구하려 하면 예외가 발생한다.")
    @Test
    void recoverFromInterruptedSend_nonRequestingMail_throwsException() {
        // given
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");

        // when & then
        assertThatThrownBy(mail::recoverFromInterruptedSend)
                .isInstanceOf(IllegalStateException.class);
    }

    @DisplayName("발송 중인 메일에 다시 발송을 시작하려 하면 예외가 발생한다.")
    @Test
    void beginAttempt_requestingMail_throwsException() {
        // given
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");
        mail.beginAttempt(REQUESTED_AT);

        // when & then
        assertThatThrownBy(() -> mail.beginAttempt(REQUESTED_AT.plusMinutes(1)))
                .isInstanceOf(IllegalStateException.class);
    }

    @DisplayName("발송할 수 없는 초대의 대기 메일을 폐기하면 시도 횟수 없이 FAILED로 종료된다.")
    @Test
    void abandon_marksMailAsFailedWithoutIncreasingAttemptCount() {
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");

        mail.abandon("취소된 초대입니다.");

        assertThat(mail.getSendStatus()).isEqualTo(MailSendStatus.FAILED);
        assertThat(mail.getAttemptCount()).isZero();
        assertThat(mail.getErrorMessage()).isEqualTo("취소된 초대입니다.");
        assertThat(mail.getInviteLink()).isNull();
    }

    @DisplayName("발송 대기 상태가 아닌 메일은 폐기할 수 없다.")
    @Test
    void abandon_nonNotRequestedMail_throwsException() {
        InvitationMail mail = InvitationMail.queue(1, "invitee@example.com", "https://example.com/invitations/token");
        mail.beginAttempt(REQUESTED_AT);

        assertThatThrownBy(() -> mail.abandon("취소된 초대입니다."))
                .isInstanceOf(IllegalStateException.class);
    }
}
