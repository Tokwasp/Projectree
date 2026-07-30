package com.ssafy.projectree.domain.project.service.result;

import com.ssafy.projectree.domain.mail.entity.MailSendStatus;

import java.time.LocalDateTime;

public record PendingInvitation(
        int invitationId,
        int inviteeMemberId,
        String inviteeName,
        String inviteeEmail,
        LocalDateTime lastInvitedAt,
        LocalDateTime expiresAt,
        boolean expired,
        MailSendStatus mailSendStatus
) {
}
