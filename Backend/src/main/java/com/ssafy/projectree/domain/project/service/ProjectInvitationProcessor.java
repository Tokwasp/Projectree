package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.mail.entity.InvitationMail;
import com.ssafy.projectree.domain.mail.repository.InvitationMailRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import com.ssafy.projectree.domain.project.entity.InvitationStatus;
import com.ssafy.projectree.domain.project.repository.ProjectInvitationRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.domain.project.service.result.InviteResult;
import com.ssafy.projectree.domain.project.service.result.MemberInviteResult;
import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;

@Service
@RequiredArgsConstructor
public class ProjectInvitationProcessor {

    private final MemberRepository memberRepository;
    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final ProjectInvitationRepository projectInvitationRepository;
    private final InvitationMailRepository invitationMailRepository;
    private final InvitationTokenGenerator invitationTokenGenerator;

    @Value("${app.invitation.base-url}")
    private String invitationBaseUrl;

    // self-invocation은 프록시를 우회해 @Transactional이 적용되지 않으므로 별도 bean으로 분리한다.
    // 대상별 독립 커밋을 보장하기 위해 REQUIRES_NEW 트랜잭션을 사용한다.
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public MemberInviteResult processInvite(int projectId, int inviterMemberId, int inviteeMemberId) {
        LocalDateTime now = LocalDateTime.now();

        if (inviterMemberId == inviteeMemberId) {
            return result(inviteeMemberId, InviteResult.SELF_INVITE);
        }

        Member invitee = memberRepository.findById(inviteeMemberId)
                .orElse(null);
        if (invitee == null) {
            return result(inviteeMemberId, InviteResult.MEMBER_NOT_FOUND);
        }

        if (projectMemberRepository.existsByProjectIdAndMemberId(projectId, inviteeMemberId)) {
            return result(inviteeMemberId, InviteResult.ALREADY_MEMBER);
        }

        ProjectInvitation invitation = projectInvitationRepository
                .findByProjectIdAndInviteeMemberId(projectId, inviteeMemberId)
                .orElse(null);

        if (invitation == null) {
            return createInvitation(projectId, inviterMemberId, invitee, now);
        }

        if (invitation.getStatus() == InvitationStatus.PENDING) {
            if (invitation.isResendCoolingDown(now)) {
                return result(inviteeMemberId, InviteResult.COOLDOWN);
            }
            return resendInvitation(invitation, invitee, now);
        }

        return reinvite(invitation, invitee, now);
    }

    private MemberInviteResult createInvitation(
            int projectId,
            int inviterMemberId,
            Member invitee,
            LocalDateTime now
    ) {
        InvitationToken token = invitationTokenGenerator.generate();
        ProjectInvitation invitation = ProjectInvitation.builder()
                .project(projectRepository.getReferenceById(projectId))
                .inviterMemberId(inviterMemberId)
                .inviteeMemberId(invitee.getId())
                .tokenHash(token.tokenHash())
                .lastInvitedAt(now)
                .build();
        ProjectInvitation savedInvitation = projectInvitationRepository.save(invitation);
        queueMail(savedInvitation.getId(), invitee.getEmail(), token.rawToken());

        return result(invitee.getId(), InviteResult.INVITED);
    }

    private MemberInviteResult resendInvitation(
            ProjectInvitation invitation,
            Member invitee,
            LocalDateTime now
    ) {
        InvitationToken token = invitationTokenGenerator.generate();
        invitation.resend(token.tokenHash(), now);
        queueMail(invitation.getId(), invitee.getEmail(), token.rawToken());

        return result(invitee.getId(), InviteResult.RESENT);
    }

    private MemberInviteResult reinvite(
            ProjectInvitation invitation,
            Member invitee,
            LocalDateTime now
    ) {
        InvitationToken token = invitationTokenGenerator.generate();
        invitation.reinvite(token.tokenHash(), now);
        queueMail(invitation.getId(), invitee.getEmail(), token.rawToken());

        return result(invitee.getId(), InviteResult.INVITED);
    }

    private void queueMail(int invitationId, String recipientEmail, String rawToken) {
        invitationMailRepository.save(InvitationMail.queue(
                invitationId,
                recipientEmail,
                invitationBaseUrl + "/invitations/" + rawToken
        ));
    }

    private MemberInviteResult result(int inviteeMemberId, InviteResult result) {
        return new MemberInviteResult(inviteeMemberId, result);
    }
}
