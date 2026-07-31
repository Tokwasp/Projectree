package com.ssafy.projectree.domain.mail.service;

import com.ssafy.projectree.domain.mail.entity.InvitationMail;
import com.ssafy.projectree.domain.mail.entity.MailSendStatus;
import com.ssafy.projectree.domain.mail.repository.InvitationMailRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import com.ssafy.projectree.domain.project.repository.ProjectInvitationRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

@Service
@RequiredArgsConstructor
public class InvitationMailSendProcessor {

    private static final String INVITATION_NOT_FOUND_REASON = "초대를 찾을 수 없습니다.";
    private static final String INVITATION_NOT_PENDING_REASON = "대기 중인 초대가 아닙니다.";
    private static final String INVITATION_EXPIRED_REASON = "만료된 초대입니다.";

    private final InvitationMailRepository invitationMailRepository;
    private final ProjectInvitationRepository projectInvitationRepository;
    private final MemberRepository memberRepository;

    @Transactional
    public Optional<InvitationMailContent> claim(long mailId, LocalDateTime now) {
        InvitationMail mail = invitationMailRepository.findById(mailId).orElse(null);
        if (mail == null || mail.getSendStatus() != MailSendStatus.NOT_REQUESTED) {
            return Optional.empty();
        }

        ProjectInvitation invitation = projectInvitationRepository.findById(mail.getInvitationId()).orElse(null);
        if (invitation == null) {
            mail.abandon(INVITATION_NOT_FOUND_REASON);
            return Optional.empty();
        }
        if (!invitation.isPending()) {
            mail.abandon(INVITATION_NOT_PENDING_REASON);
            return Optional.empty();
        }
        if (invitation.isExpired(now)) {
            mail.abandon(INVITATION_EXPIRED_REASON);
            return Optional.empty();
        }

        Member inviter = memberRepository.findById(invitation.getInviterMemberId()).orElseThrow();
        mail.beginAttempt(now);
        return Optional.of(new InvitationMailContent(
                mail.getId(),
                mail.getRecipientEmail(),
                mail.getInviteLink(),
                invitation.getProject().getTitle(),
                inviter.getName()
        ));
    }

    @Transactional
    public void recordSuccess(long mailId) {
        invitationMailRepository.findById(mailId).orElseThrow().succeed();
    }

    @Transactional
    public void recordFailure(long mailId, String reason) {
        invitationMailRepository.findById(mailId).orElseThrow().fail(reason);
    }

    @Transactional
    public int recoverInterruptedSends(LocalDateTime cutoff) {
        List<InvitationMail> mails = invitationMailRepository
                .findAllBySendStatusAndUpdatedAtBefore(MailSendStatus.REQUESTING, cutoff);
        mails.forEach(InvitationMail::recoverFromInterruptedSend);
        return mails.size();
    }
}

record InvitationMailContent(
        long mailId,
        String recipientEmail,
        String inviteLink,
        String projectTitle,
        String inviterName
) {
}
