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
import com.ssafy.projectree.domain.project.exception.InvitationErrorCode;
import com.ssafy.projectree.domain.project.exception.ProjectErrorCode;
import com.ssafy.projectree.domain.project.repository.ProjectInvitationRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.domain.project.service.result.InviteResult;
import com.ssafy.projectree.domain.project.service.result.InvitationLanding;
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
        projectMemberRepository.deleteAll();
        projectRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @DisplayName("초대 대상 회원은 초대를 수락해 프로젝트 멤버가 된다.")
    @Test
    void acceptInvitation_acceptsAndAddsProjectMember() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "accept-token";
        ProjectInvitation invitation = saveInvitationForToken(
                project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now()
        );

        int joinedProjectId = projectInvitationService.acceptInvitation(rawToken, invitee.getId());

        ProjectInvitation found = projectInvitationRepository.findById(invitation.getId()).orElseThrow();
        assertThat(joinedProjectId).isEqualTo(project.getId());
        assertThat(found.getStatus()).isEqualTo(InvitationStatus.ACCEPTED);
        assertThat(found.getAcceptedAt()).isNotNull();
        assertThat(projectMemberRepository.existsByProjectIdAndMemberIdAndRole(
                project.getId(), invitee.getId(), ProjectRole.MEMBER
        )).isTrue();
    }

    @DisplayName("존재하지 않는 토큰으로 수락하면 초대를 찾을 수 없다.")
    @Test
    void acceptInvitation_invalidToken_throwsException() {
        assertThatThrownBy(() -> projectInvitationService.acceptInvitation("invalid-token", 1))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(InvitationErrorCode.INVITATION_NOT_FOUND);
    }

    @DisplayName("다른 회원은 초대를 수락할 수 없다.")
    @Test
    void acceptInvitation_inviteeMismatch_throwsException() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Member anotherMember = saveMember("another@example.com", "다른 회원");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "mismatch-token";
        ProjectInvitation invitation = saveInvitationForToken(
                project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now()
        );

        assertThatThrownBy(() -> projectInvitationService.acceptInvitation(rawToken, anotherMember.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(InvitationErrorCode.INVITATION_INVITEE_MISMATCH);

        assertThat(projectInvitationRepository.findById(invitation.getId()).orElseThrow().getStatus())
                .isEqualTo(InvitationStatus.PENDING);
        assertThat(projectMemberRepository.existsByProjectIdAndMemberId(project.getId(), anotherMember.getId()))
                .isFalse();
    }

    @DisplayName("만료된 초대는 수락할 수 없다.")
    @Test
    void acceptInvitation_expiredInvitation_throwsException() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "expired-accept-token";
        saveInvitationForToken(project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now().minusHours(25));

        assertThatThrownBy(() -> projectInvitationService.acceptInvitation(rawToken, invitee.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(InvitationErrorCode.INVITATION_EXPIRED);
        assertThat(projectMemberRepository.existsByProjectIdAndMemberId(project.getId(), invitee.getId())).isFalse();
    }

    @DisplayName("이미 수락한 초대를 다시 수락하면 처리 완료 예외가 발생한다.")
    @Test
    void acceptInvitation_alreadyAcceptedInvitation_throwsException() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "double-accept-token";
        saveInvitationForToken(project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now());
        projectInvitationService.acceptInvitation(rawToken, invitee.getId());

        assertThatThrownBy(() -> projectInvitationService.acceptInvitation(rawToken, invitee.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(InvitationErrorCode.INVITATION_NOT_PENDING);
    }

    @DisplayName("이미 프로젝트 멤버인 초대 대상은 수락할 수 없고 초대는 대기 상태로 유지된다.")
    @Test
    void acceptInvitation_alreadyProjectMember_throwsException() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId(), invitee.getId());
        String rawToken = "already-member-token";
        ProjectInvitation invitation = saveInvitationForToken(
                project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now()
        );

        assertThatThrownBy(() -> projectInvitationService.acceptInvitation(rawToken, invitee.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.ALREADY_PROJECT_MEMBER);
        assertThat(projectInvitationRepository.findById(invitation.getId()).orElseThrow().getStatus())
                .isEqualTo(InvitationStatus.PENDING);
    }

    @DisplayName("초대 대상 회원은 초대를 거절할 수 있다.")
    @Test
    void rejectInvitation_rejectsInvitation() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "reject-token";
        ProjectInvitation invitation = saveInvitationForToken(
                project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now()
        );

        projectInvitationService.rejectInvitation(rawToken, invitee.getId());

        ProjectInvitation found = projectInvitationRepository.findById(invitation.getId()).orElseThrow();
        assertThat(found.getStatus()).isEqualTo(InvitationStatus.REJECTED);
        assertThat(found.getRejectedAt()).isNotNull();
        assertThat(projectMemberRepository.existsByProjectIdAndMemberId(project.getId(), invitee.getId())).isFalse();
    }

    @DisplayName("다른 회원은 초대를 거절할 수 없다.")
    @Test
    void rejectInvitation_inviteeMismatch_throwsException() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Member anotherMember = saveMember("another@example.com", "다른 회원");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "reject-mismatch-token";
        saveInvitationForToken(project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now());

        assertThatThrownBy(() -> projectInvitationService.rejectInvitation(rawToken, anotherMember.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(InvitationErrorCode.INVITATION_INVITEE_MISMATCH);
    }

    @DisplayName("만료된 초대는 거절할 수 없다.")
    @Test
    void rejectInvitation_expiredInvitation_throwsException() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "expired-reject-token";
        saveInvitationForToken(project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now().minusHours(25));

        assertThatThrownBy(() -> projectInvitationService.rejectInvitation(rawToken, invitee.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(InvitationErrorCode.INVITATION_EXPIRED);
    }

    @DisplayName("초대 랜딩 조회는 프로젝트와 초대자 정보를 반환한다.")
    @Test
    void getLanding_returnsInvitationInformation() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "landing-token";
        saveInvitationForToken(project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now());

        InvitationLanding landing = projectInvitationService.getLanding(rawToken, invitee.getId());

        assertThat(landing).isEqualTo(new InvitationLanding(
                project.getTitle(), owner.getName(), InvitationStatus.PENDING, false
        ));
    }

    @DisplayName("만료된 대기 초대도 랜딩 조회에서는 상태와 만료 여부를 반환한다.")
    @Test
    void getLanding_expiredPendingInvitation_returnsExpired() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "expired-landing-token";
        saveInvitationForToken(project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now().minusHours(25));

        InvitationLanding landing = projectInvitationService.getLanding(rawToken, invitee.getId());

        assertThat(landing.status()).isEqualTo(InvitationStatus.PENDING);
        assertThat(landing.expired()).isTrue();
    }

    @DisplayName("처리 완료된 초대도 랜딩 조회에서는 상태를 반환한다.")
    @Test
    void getLanding_rejectedInvitation_returnsRejectedStatus() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "rejected-landing-token";
        ProjectInvitation invitation = saveInvitationForToken(
                project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now()
        );
        invitation.reject(LocalDateTime.now());
        projectInvitationRepository.saveAndFlush(invitation);

        InvitationLanding landing = projectInvitationService.getLanding(rawToken, invitee.getId());

        assertThat(landing.status()).isEqualTo(InvitationStatus.REJECTED);
        assertThat(landing.expired()).isFalse();
    }

    @DisplayName("무효 토큰으로 랜딩을 조회하면 초대를 찾을 수 없다.")
    @Test
    void getLanding_invalidToken_throwsException() {
        assertThatThrownBy(() -> projectInvitationService.getLanding("invalid-token", 1))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(InvitationErrorCode.INVITATION_NOT_FOUND);
    }

    @DisplayName("다른 회원은 초대 랜딩을 조회할 수 없다.")
    @Test
    void getLanding_inviteeMismatch_throwsException() {
        Member owner = saveMember("owner@example.com", "소유자");
        Member invitee = saveMember("invitee@example.com", "초대 대상");
        Member anotherMember = saveMember("another@example.com", "다른 회원");
        Project project = saveProjectWithMembers(owner.getId());
        String rawToken = "landing-mismatch-token";
        saveInvitationForToken(project, owner.getId(), invitee.getId(), rawToken, LocalDateTime.now());

        assertThatThrownBy(() -> projectInvitationService.getLanding(rawToken, anotherMember.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(InvitationErrorCode.INVITATION_INVITEE_MISMATCH);
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

    private ProjectInvitation saveInvitationForToken(
            Project project,
            int inviterMemberId,
            int inviteeMemberId,
            String rawToken,
            LocalDateTime invitedAt
    ) {
        return saveInvitation(
                project,
                inviterMemberId,
                inviteeMemberId,
                invitationTokenGenerator.hash(rawToken),
                invitedAt
        );
    }
}
