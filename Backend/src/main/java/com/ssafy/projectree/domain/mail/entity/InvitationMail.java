package com.ssafy.projectree.domain.mail.entity;

import com.ssafy.projectree.global.entity.BaseEntity;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import lombok.AccessLevel;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.Objects;

@Entity
@Table(
        name = "project_invitation_mail",
        indexes = {
                @Index(
                        name = "idx_invitation_mail_outbox",
                        columnList = "send_status, updated_at"
                ),
                @Index(
                        name = "idx_invitation_mail_invitation",
                        columnList = "invitation_id, id"
                )
        }
)
/**
 * NOT_REQUESTED 상태의 행은 항상 최대 발송 시도 횟수보다 작은 시도 횟수를 가진다.
 */
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class InvitationMail extends BaseEntity {

    private static final int MAX_ATTEMPT_COUNT = 3;
    private static final int MAX_ERROR_MESSAGE_LENGTH = 500;
    private static final String INTERRUPTED_SEND_MESSAGE = "발송 도중 서버가 중단되었습니다.";

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private long id;

    @Column(name = "invitation_id", nullable = false)
    private int invitationId;

    @Enumerated(EnumType.STRING)
    @Column(name = "send_status", nullable = false, length = 20)
    private MailSendStatus sendStatus;

    @Column(name = "attempt_count", nullable = false)
    private int attemptCount;

    @Column(name = "recipient_email", nullable = false, length = 255)
    private String recipientEmail;

    @Column(name = "invite_link", length = 500)
    private String inviteLink;

    @Column(name = "error_message", length = MAX_ERROR_MESSAGE_LENGTH)
    private String errorMessage;

    @Column(name = "requested_at")
    private LocalDateTime requestedAt;

    private InvitationMail(int invitationId, String recipientEmail, String inviteLink) {
        this.invitationId = invitationId;
        this.recipientEmail = Objects.requireNonNull(recipientEmail);
        this.inviteLink = Objects.requireNonNull(inviteLink);
        this.sendStatus = MailSendStatus.NOT_REQUESTED;
        this.attemptCount = 0;
    }

    public static InvitationMail queue(int invitationId, String recipientEmail, String inviteLink) {
        return new InvitationMail(invitationId, recipientEmail, inviteLink);
    }

    public void beginAttempt(LocalDateTime now) {
        if (sendStatus != MailSendStatus.NOT_REQUESTED) {
            throw new IllegalStateException("발송 대기 상태에서만 발송을 시작할 수 있습니다.");
        }

        sendStatus = MailSendStatus.REQUESTING;
        attemptCount++;
        requestedAt = Objects.requireNonNull(now);
    }

    public void succeed() {
        requireRequestingState();
        sendStatus = MailSendStatus.SENT;
        errorMessage = null;
        inviteLink = null;
    }

    public void fail(String reason) {
        requireRequestingState();
        errorMessage = truncate(Objects.requireNonNull(reason));
        transitionToRetryOrFailed();
    }

    public void recoverFromInterruptedSend() {
        requireRequestingState();
        errorMessage = INTERRUPTED_SEND_MESSAGE;
        transitionToRetryOrFailed();
    }

    /**
     * NOT_REQUESTED 상태는 항상 재시도 가능한 시도 횟수를 가진다는 불변식을 유지한다.
     * 발송할 수 없는 초대의 메일은 시도 횟수를 소모하지 않고 즉시 종결한다.
     */
    public void abandon(String reason) {
        if (sendStatus != MailSendStatus.NOT_REQUESTED) {
            throw new IllegalStateException("발송 대기 상태의 메일만 폐기할 수 있습니다.");
        }

        errorMessage = truncate(Objects.requireNonNull(reason));
        sendStatus = MailSendStatus.FAILED;
        inviteLink = null;
    }

    private void transitionToRetryOrFailed() {
        if (attemptCount >= MAX_ATTEMPT_COUNT) {
            sendStatus = MailSendStatus.FAILED;
            inviteLink = null;
            return;
        }

        sendStatus = MailSendStatus.NOT_REQUESTED;
    }

    public boolean isTerminal() {
        return sendStatus == MailSendStatus.SENT || sendStatus == MailSendStatus.FAILED;
    }

    private void requireRequestingState() {
        if (sendStatus != MailSendStatus.REQUESTING) {
            throw new IllegalStateException("발송 중인 메일만 처리할 수 있습니다.");
        }
    }

    private String truncate(String reason) {
        return reason.length() <= MAX_ERROR_MESSAGE_LENGTH
                ? reason
                : reason.substring(0, MAX_ERROR_MESSAGE_LENGTH);
    }
}
