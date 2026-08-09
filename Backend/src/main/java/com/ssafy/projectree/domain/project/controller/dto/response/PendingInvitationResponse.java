package com.ssafy.projectree.domain.project.controller.dto.response;

import com.ssafy.projectree.domain.mail.entity.MailSendStatus;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
public class PendingInvitationResponse {

    private final int invitationId;
    private final int inviteeMemberId;
    private final String inviteeName;
    private final String inviteeEmail;
    private final LocalDateTime lastInvitedAt;
    private final LocalDateTime expiresAt;
    private final boolean expired;
    private final MailSendStatus mailSendStatus;

    private PendingInvitationResponse(
            int invitationId,
            int inviteeMemberId,
            String inviteeName,
            String inviteeEmail,
            LocalDateTime lastInvitedAt,
            LocalDateTime expiresAt,
            boolean expired,
            MailSendStatus mailSendStatus
    ) {
        this.invitationId = invitationId;
        this.inviteeMemberId = inviteeMemberId;
        this.inviteeName = inviteeName;
        this.inviteeEmail = inviteeEmail;
        this.lastInvitedAt = lastInvitedAt;
        this.expiresAt = expiresAt;
        this.expired = expired;
        this.mailSendStatus = mailSendStatus;
    }

    public static PendingInvitationResponse of(
            ProjectInvitation invitation,
            Member invitee,
            MailSendStatus mailSendStatus,
            LocalDateTime now
    ) {
        return new PendingInvitationResponse(
                invitation.getId(),
                invitation.getInviteeMemberId(),
                invitee.getName(),
                invitee.getEmail(),
                invitation.getLastInvitedAt(),
                invitation.getExpiresAt(),
                invitation.isExpired(now),
                mailSendStatus
        );
    }
}
