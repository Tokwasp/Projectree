package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.mail.entity.InvitationMail;
import com.ssafy.projectree.domain.mail.entity.MailSendStatus;
import com.ssafy.projectree.domain.mail.repository.InvitationMailRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.entity.InvitationStatus;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.exception.ProjectErrorCode;
import com.ssafy.projectree.domain.project.repository.ProjectInvitationRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.domain.project.service.result.InviteResult;
import com.ssafy.projectree.domain.project.service.result.MemberInviteResult;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Transactional(propagation = Propagation.NOT_SUPPORTED)
class ProjectInvitationServiceTest extends IntegrationTestSupport {

    private static final String INVITATION_BASE_URL = "https://projectree.site/invitations/";

    @Autowired
    private ProjectInvitationService projectInvitationService;

    @Autowired
    private InvitationTokenGenerator invitationTokenGenerator;

    @Autowired
    private MemberRepository memberRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private ProjectInvitationRepository projectInvitationRepository;

    @Autowired
    private ProjectMemberRepository projectMemberRepository;

    @Autowired
    private InvitationMailRepository invitationMailRepository;

    @AfterEach
    void clearDatabase() {
        invitationMailRepository.deleteAll();
        projectInvitationRepository.deleteAll();
        projectRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @DisplayName("신규 초대 시 초대와 발송 대기 메일이 함께 저장된다.")
    @Test
    void invite_newInvitation() {
        // given
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());

        // when
        List<MemberInviteResult> results = projectInvitationService.invite(
                project.getId(), owner.getId(), List.of(invitee.getId())
        );

        // then
        assertThat(results).containsExactly(new MemberInviteResult(invitee.getId(), InviteResult.INVITED));
        ProjectInvitation invitation = projectInvitationRepository
                .findByProjectIdAndInviteeMemberId(project.getId(), invitee.getId())
                .orElseThrow();
        InvitationMail mail = invitationMailRepository.findAll().getFirst();
        String rawToken = mail.getInviteLink().substring(INVITATION_BASE_URL.length());

        assertThat(invitation.getStatus()).isEqualTo(InvitationStatus.PENDING);
        assertThat(mail.getSendStatus()).isEqualTo(MailSendStatus.NOT_REQUESTED);
        assertThat(mail.getInvitationId()).isEqualTo(invitation.getId());
        assertThat(mail.getInviteLink()).startsWith(INVITATION_BASE_URL);
        assertThat(invitationTokenGenerator.hash(rawToken)).isEqualTo(invitation.getTokenHash());
    }

    @DisplayName("쿨다운이 지난 PENDING 초대를 다시 요청하면 토큰을 갱신하고 메일을 추가한다.")
    @Test
    void invite_pendingInvitation_resends() {
        // given
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        ProjectInvitation invitation = saveInvitation(
                project, owner.getId(), invitee.getId(), "old-token", LocalDateTime.now().minusMinutes(2)
        );
        invitationMailRepository.saveAndFlush(InvitationMail.queue(
                invitation.getId(), invitee.getEmail(), INVITATION_BASE_URL + "old-token"
        ));

        // when
        List<MemberInviteResult> results = projectInvitationService.invite(
                project.getId(), owner.getId(), List.of(invitee.getId())
        );

        // then
        ProjectInvitation found = projectInvitationRepository.findById(invitation.getId()).orElseThrow();
        assertThat(results).containsExactly(new MemberInviteResult(invitee.getId(), InviteResult.RESENT));
        assertThat(found.getTokenHash()).isNotEqualTo("old-token");
        assertThat(invitationMailRepository.findAll()).hasSize(2);
    }

    @DisplayName("방금 만든 초대를 다시 요청하면 쿨다운으로 처리되고 메일을 추가하지 않는다.")
    @Test
    void invite_pendingInvitationWithinCooldown() {
        // given
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        projectInvitationService.invite(project.getId(), owner.getId(), List.of(invitee.getId()));
        ProjectInvitation invitation = projectInvitationRepository
                .findByProjectIdAndInviteeMemberId(project.getId(), invitee.getId())
                .orElseThrow();
        String previousTokenHash = invitation.getTokenHash();

        // when
        List<MemberInviteResult> results = projectInvitationService.invite(
                project.getId(), owner.getId(), List.of(invitee.getId())
        );

        // then
        assertThat(results).containsExactly(new MemberInviteResult(invitee.getId(), InviteResult.COOLDOWN));
        assertThat(projectInvitationRepository.findById(invitation.getId()).orElseThrow().getTokenHash())
                .isEqualTo(previousTokenHash);
        assertThat(invitationMailRepository.findAll()).hasSize(1);
    }

    @DisplayName("거절된 초대를 다시 요청하면 PENDING 상태의 새 초대로 되살린다.")
    @Test
    void invite_rejectedInvitation_reinvites() {
        // given
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        ProjectInvitation invitation = ProjectInvitation.builder()
                .project(project)
                .inviterMemberId(owner.getId())
                .inviteeMemberId(invitee.getId())
                .tokenHash("old-token")
                .lastInvitedAt(LocalDateTime.now())
                .build();
        invitation.reject(LocalDateTime.now());
        projectInvitationRepository.saveAndFlush(invitation);

        // when
        List<MemberInviteResult> results = projectInvitationService.invite(
                project.getId(), owner.getId(), List.of(invitee.getId())
        );

        // then
        assertThat(results).containsExactly(new MemberInviteResult(invitee.getId(), InviteResult.INVITED));
        assertThat(projectInvitationRepository.findById(invitation.getId()).orElseThrow().getStatus())
                .isEqualTo(InvitationStatus.PENDING);
    }

    @DisplayName("다건 초대는 대상별 실패를 결과로 반환하고 정상 대상만 저장한다.")
    @Test
    void invite_returnsPerInviteeResults() {
        // given
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Member alreadyMember = saveMember("member@example.com", "기존 멤버");
        Project project = saveProjectWithMembers(owner.getId(), alreadyMember.getId());

        // when
        List<MemberInviteResult> results = projectInvitationService.invite(
                project.getId(),
                owner.getId(),
                List.of(invitee.getId(), owner.getId(), 999_999, alreadyMember.getId())
        );

        // then
        assertThat(results).containsExactly(
                new MemberInviteResult(invitee.getId(), InviteResult.INVITED),
                new MemberInviteResult(owner.getId(), InviteResult.SELF_INVITE),
                new MemberInviteResult(999_999, InviteResult.MEMBER_NOT_FOUND),
                new MemberInviteResult(alreadyMember.getId(), InviteResult.ALREADY_MEMBER)
        );
        assertThat(projectInvitationRepository.count()).isEqualTo(1);
        assertThat(invitationMailRepository.count()).isEqualTo(1);
    }

    @DisplayName("존재하지 않는 프로젝트에 초대하면 PROJECT_NOT_FOUND 예외가 발생한다.")
    @Test
    void invite_projectNotFound_throwsException() {
        // given
        Member owner = saveMember("owner@example.com", "소유자");

        // when & then
        assertThatThrownBy(() -> projectInvitationService.invite(999_999, owner.getId(), List.of(2)))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("OWNER가 아닌 회원이나 비멤버가 초대하면 NOT_PROJECT_OWNER 예외가 발생한다.")
    @Test
    void invite_notProjectOwner_throwsException() {
        // given
        Member owner = saveMember("owner@example.com", "소유자");
        Member member = saveMember("member@example.com", "멤버");
        Member outsider = saveMember("outsider@example.com", "비멤버");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId(), member.getId());

        // when & then
        assertThatThrownBy(() -> projectInvitationService.invite(
                project.getId(), member.getId(), List.of(invitee.getId())
        )).isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.NOT_PROJECT_OWNER);

        assertThatThrownBy(() -> projectInvitationService.invite(
                project.getId(), outsider.getId(), List.of(invitee.getId())
        )).isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.NOT_PROJECT_OWNER);
    }

    private Member saveMember(String email, String name) {
        return memberRepository.saveAndFlush(Member.builder()
                .email(email)
                .name(name)
                .build());
    }

    private Project saveProjectWithMembers(int ownerMemberId, int... memberIds) {
        Project project = Project.builder()
                .title("프로젝트 초대")
                .content("프로젝트 초대 서비스 테스트입니다.")
                .build();
        project.addMember(ProjectMember.createMember(ownerMemberId, ProjectRole.OWNER));
        for (int memberId : memberIds) {
            project.addMember(ProjectMember.createMember(memberId, ProjectRole.MEMBER));
        }
        return projectRepository.saveAndFlush(project);
    }

    private ProjectInvitation saveInvitation(
            Project project,
            int inviterMemberId,
            int inviteeMemberId,
            String tokenHash,
            LocalDateTime invitedAt
    ) {
        return projectInvitationRepository.saveAndFlush(ProjectInvitation.builder()
                .project(project)
                .inviterMemberId(inviterMemberId)
                .inviteeMemberId(inviteeMemberId)
                .tokenHash(tokenHash)
                .lastInvitedAt(invitedAt)
                .build());
    }
}
