package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.exception.ProjectErrorCode;
import com.ssafy.projectree.domain.project.exception.InvitationErrorCode;
import com.ssafy.projectree.domain.project.repository.ProjectInvitationRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.service.result.InviteResult;
import com.ssafy.projectree.domain.project.service.result.MemberInviteResult;
import com.ssafy.projectree.domain.project.service.result.InvitationLanding;
import com.ssafy.projectree.global.exception.CustomException;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Service
@Slf4j
@RequiredArgsConstructor
public class ProjectInvitationService {

    private final ProjectRepository projectRepository;
    private final ProjectMemberRepository projectMemberRepository;
    private final ProjectInvitationRepository projectInvitationRepository;
    private final MemberRepository memberRepository;
    private final InvitationTokenGenerator invitationTokenGenerator;
    private final ProjectInvitationProcessor projectInvitationProcessor;

    public List<MemberInviteResult> invite(
            int projectId,
            int inviterMemberId,
            List<Integer> inviteeMemberIds
    ) {
        validateProjectAndOwner(projectId, inviterMemberId);

        List<MemberInviteResult> results = new ArrayList<>();
        for (int inviteeMemberId : inviteeMemberIds) {
            results.add(processInvite(projectId, inviterMemberId, inviteeMemberId));
        }
        return results;
    }

    @Transactional(readOnly = true)
    public InvitationLanding getLanding(String rawToken, int loginMemberId) {
        LocalDateTime now = LocalDateTime.now();
        ProjectInvitation invitation = findInvitation(rawToken);
        validateInvitee(invitation, loginMemberId);

        Member inviter = memberRepository.findById(invitation.getInviterMemberId()).orElseThrow();
        return new InvitationLanding(
                invitation.getProject().getTitle(),
                inviter.getName(),
                invitation.getStatus(),
                invitation.isExpired(now)
        );
    }

    /**
     * 비관적 락을 보유하는 동안에는 상태 전이와 멤버 저장만 수행한다.
     * 외부 호출이나 무거운 조회를 추가하지 않아 락 대기 시간을 최소화한다.
     */
    @Transactional
    public int acceptInvitation(String rawToken, int loginMemberId) {
        LocalDateTime now = LocalDateTime.now();
        ProjectInvitation invitation = findInvitationWithLockFor(rawToken, loginMemberId);

        int projectId = invitation.getProject().getId();
        invitation.accept(now);
        if (projectMemberRepository.existsByProjectIdAndMemberId(projectId, loginMemberId)) {
            throw new CustomException(ProjectErrorCode.ALREADY_PROJECT_MEMBER);
        }

        ProjectMember projectMember = ProjectMember.createMember(loginMemberId, ProjectRole.MEMBER);
        projectMember.assignProject(invitation.getProject());

        try {
            // 프로젝트 멤버 컬렉션 전체를 불러오지 않기 위해 project.addMember() 대신 직접 저장한다.
            projectMemberRepository.saveAndFlush(projectMember);
        } catch (DataIntegrityViolationException e) {
            log.warn("프로젝트 멤버 저장 중 무결성 위반, 이미 멤버로 처리: {}", e.getMessage());
            throw new CustomException(ProjectErrorCode.ALREADY_PROJECT_MEMBER);
        }

        return projectId;
    }

    @Transactional
    public void rejectInvitation(String rawToken, int loginMemberId) {
        LocalDateTime now = LocalDateTime.now();
        ProjectInvitation invitation = findInvitationWithLockFor(rawToken, loginMemberId);

        invitation.reject(now);
    }

    private void validateProjectAndOwner(int projectId, int inviterMemberId) {
        if (!projectRepository.existsById(projectId)) {
            throw new CustomException(ProjectErrorCode.PROJECT_NOT_FOUND);
        }
        if (!projectMemberRepository.existsByProjectIdAndMemberIdAndRole(
                projectId, inviterMemberId, ProjectRole.OWNER
        )) {
            throw new CustomException(ProjectErrorCode.NOT_PROJECT_OWNER);
        }
    }

    private MemberInviteResult processInvite(int projectId, int inviterMemberId, int inviteeMemberId) {
        try {
            return projectInvitationProcessor.processInvite(projectId, inviterMemberId, inviteeMemberId);
        } catch (DataIntegrityViolationException e) {
            // 동시 초대로 유니크 제약에 걸린 대상은 방금 생성된 초대와 같은 쿨다운으로 처리한다.
            log.warn("초대 저장 중 무결성 위반, COOLDOWN으로 처리: {}", e.getMessage());
            return new MemberInviteResult(inviteeMemberId, InviteResult.COOLDOWN);
        }
    }

    private ProjectInvitation findInvitation(String rawToken) {
        String tokenHash = invitationTokenGenerator.hash(rawToken);
        return projectInvitationRepository.findByTokenHash(tokenHash)
                .orElseThrow(() -> new CustomException(InvitationErrorCode.INVITATION_NOT_FOUND));
    }

    private ProjectInvitation findInvitationWithLockFor(String rawToken, int loginMemberId) {
        String tokenHash = invitationTokenGenerator.hash(rawToken);
        ProjectInvitation invitation = projectInvitationRepository.findWithLockByTokenHash(tokenHash)
                .orElseThrow(() -> new CustomException(InvitationErrorCode.INVITATION_NOT_FOUND));
        validateInvitee(invitation, loginMemberId);
        return invitation;
    }

    private void validateInvitee(ProjectInvitation invitation, int loginMemberId) {
        if (!invitation.isInviteeOf(loginMemberId)) {
            throw new CustomException(InvitationErrorCode.INVITATION_INVITEE_MISMATCH);
        }
    }
}
