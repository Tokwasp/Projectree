package com.ssafy.projectree.domain.project.entity;

import com.ssafy.projectree.domain.project.exception.InvitationErrorCode;
import com.ssafy.projectree.global.entity.BaseEntity;
import com.ssafy.projectree.global.exception.CustomException;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import lombok.AccessLevel;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Objects;

@Entity
@Table(
        name = "project_invitation",
        uniqueConstraints = {
                @UniqueConstraint(
                        name = "uk_project_invitation",
                        columnNames = {"project_id", "invitee_member_id"}
                ),
                @UniqueConstraint(
                        name = "uk_project_invitation_token_hash",
                        columnNames = "token_hash"
                )
        },
        indexes = @Index(
                name = "idx_project_invitation_invitee",
                columnList = "invitee_member_id, status"
        )
)
@Getter
@NoArgsConstructor(access = AccessLevel.PROTECTED)
public class ProjectInvitation extends BaseEntity {

    private static final Duration EXPIRY = Duration.ofHours(24);
    private static final Duration RESEND_COOLDOWN = Duration.ofSeconds(60);

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private int id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "project_id", nullable = false)
    private Project project;

    @Column(name = "inviter_member_id", nullable = false)
    private int inviterMemberId;

    @Column(name = "invitee_member_id", nullable = false)
    private int inviteeMemberId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private InvitationStatus status;

    @Column(name = "token_hash", nullable = false, length = 64)
    private String tokenHash;

    @Column(name = "last_invited_at", nullable = false)
    private LocalDateTime lastInvitedAt;

    @Column(name = "expires_at", nullable = false)
    private LocalDateTime expiresAt;

    @Column(name = "accepted_at")
    private LocalDateTime acceptedAt;

    @Column(name = "rejected_at")
    private LocalDateTime rejectedAt;

    @Column(name = "canceled_at")
    private LocalDateTime canceledAt;

    @Builder
    private ProjectInvitation(
            Project project,
            int inviterMemberId,
            int inviteeMemberId,
            String tokenHash,
            LocalDateTime lastInvitedAt
    ) {
        if (inviterMemberId == inviteeMemberId) {
            throw new IllegalArgumentException("초대자와 초대 대상자는 같을 수 없습니다.");
        }

        this.project = Objects.requireNonNull(project);
        this.inviterMemberId = inviterMemberId;
        this.inviteeMemberId = inviteeMemberId;
        this.tokenHash = Objects.requireNonNull(tokenHash);
        this.lastInvitedAt = Objects.requireNonNull(lastInvitedAt);
        this.expiresAt = lastInvitedAt.plus(EXPIRY);
        this.status = InvitationStatus.PENDING;
    }

    public boolean isExpired(LocalDateTime now) {
        return status == InvitationStatus.PENDING && !now.isBefore(expiresAt);
    }

    public boolean isResendCoolingDown(LocalDateTime now) {
        return now.isBefore(lastInvitedAt.plus(RESEND_COOLDOWN));
    }

    public boolean isPending() {
        return status == InvitationStatus.PENDING;
    }

    public boolean isInviteeOf(int memberId) {
        return inviteeMemberId == memberId;
    }

    public void resend(String newTokenHash, LocalDateTime now) {
        requirePendingState();
        renewInvitation(newTokenHash, now);
    }

    public void reinvite(String newTokenHash, LocalDateTime now) {
        if (isPending()) {
            throw new IllegalStateException("대기 중인 초대는 재초대할 수 없습니다.");
        }

        acceptedAt = null;
        rejectedAt = null;
        canceledAt = null;
        status = InvitationStatus.PENDING;
        renewInvitation(newTokenHash, now);
    }

    public void accept(LocalDateTime now) {
        validateActionable(now);
        status = InvitationStatus.ACCEPTED;
        acceptedAt = now;
    }

    public void reject(LocalDateTime now) {
        validateActionable(now);
        status = InvitationStatus.REJECTED;
        rejectedAt = now;
    }

    public void cancel(LocalDateTime now) {
        requirePendingState();
        status = InvitationStatus.CANCELED;
        canceledAt = now;
    }

    private void renewInvitation(String newTokenHash, LocalDateTime now) {
        tokenHash = Objects.requireNonNull(newTokenHash);
        lastInvitedAt = Objects.requireNonNull(now);
        expiresAt = now.plus(EXPIRY);
    }

    private void validateActionable(LocalDateTime now) {
        requirePendingState();
        if (isExpired(now)) {
            throw new CustomException(InvitationErrorCode.INVITATION_EXPIRED);
        }
    }

    private void requirePendingState() {
        if (!isPending()) {
            throw new CustomException(InvitationErrorCode.INVITATION_NOT_PENDING);
        }
    }
}
