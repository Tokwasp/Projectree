package com.ssafy.projectree.domain.mail.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.mail.entity.InvitationMail;
import com.ssafy.projectree.domain.mail.entity.MailSendStatus;
import com.ssafy.projectree.domain.mail.repository.InvitationMailRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectInvitationRepository;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.then;
import static org.mockito.Mockito.doAnswer;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.never;

@Transactional(propagation = Propagation.NOT_SUPPORTED)
class InvitationMailSweeperTest extends IntegrationTestSupport {

    @Autowired
    private InvitationMailSweeper invitationMailSweeper;

    @Autowired
    private InvitationMailRepository invitationMailRepository;

    @Autowired
    private ProjectInvitationRepository projectInvitationRepository;

    @Autowired
    private ProjectMemberRepository projectMemberRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private MemberRepository memberRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @MockitoBean
    private InvitationMailClient invitationMailClient;

    @AfterEach
    void clearDatabase() {
        invitationMailRepository.deleteAll();
        projectInvitationRepository.deleteAll();
        projectMemberRepository.deleteAll();
        projectRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @Test
    void sweep_sendsPendingMailAndRecordsSuccess() {
        InvitationFixture fixture = createInvitationFixture("invitee@example.com", LocalDateTime.now());
        InvitationMail mail = saveMail(fixture.invitation(), fixture.invitee().getEmail());

        invitationMailSweeper.sweep();

        InvitationMail found = invitationMailRepository.findById(mail.getId()).orElseThrow();
        ArgumentCaptor<InvitationMailContent> contentCaptor = ArgumentCaptor.forClass(InvitationMailContent.class);
        then(invitationMailClient).should().send(contentCaptor.capture());
        assertThat(found.getSendStatus()).isEqualTo(MailSendStatus.SENT);
        assertThat(found.getInviteLink()).isNull();
        assertThat(contentCaptor.getValue().projectTitle()).isEqualTo(fixture.project().getTitle());
        assertThat(contentCaptor.getValue().inviterName()).isEqualTo(fixture.owner().getName());
    }

    @Test
    void sweep_retriesFailedMailAndEventuallyMarksItFailed() {
        InvitationFixture fixture = createInvitationFixture("invitee@example.com", LocalDateTime.now());
        InvitationMail mail = saveMail(fixture.invitation(), fixture.invitee().getEmail());
        doThrow(new IllegalStateException("SMTP 연결 실패"))
                .when(invitationMailClient).send(any(InvitationMailContent.class));

        invitationMailSweeper.sweep();

        InvitationMail firstAttempt = invitationMailRepository.findById(mail.getId()).orElseThrow();
        assertThat(firstAttempt.getSendStatus()).isEqualTo(MailSendStatus.NOT_REQUESTED);
        assertThat(firstAttempt.getAttemptCount()).isEqualTo(1);
        assertThat(firstAttempt.getErrorMessage()).isEqualTo("SMTP 연결 실패");

        invitationMailSweeper.sweep();
        invitationMailSweeper.sweep();

        InvitationMail found = invitationMailRepository.findById(mail.getId()).orElseThrow();
        assertThat(found.getSendStatus()).isEqualTo(MailSendStatus.FAILED);
        assertThat(found.getAttemptCount()).isEqualTo(3);
        assertThat(found.getInviteLink()).isNull();
    }

    @Test
    void sweep_recordsExceptionTypeWhenMailClientExceptionHasNoMessage() {
        InvitationFixture fixture = createInvitationFixture("invitee@example.com", LocalDateTime.now());
        InvitationMail mail = saveMail(fixture.invitation(), fixture.invitee().getEmail());
        doThrow(new IllegalStateException())
                .when(invitationMailClient).send(any(InvitationMailContent.class));

        invitationMailSweeper.sweep();

        InvitationMail found = invitationMailRepository.findById(mail.getId()).orElseThrow();
        assertThat(found.getSendStatus()).isEqualTo(MailSendStatus.NOT_REQUESTED);
        assertThat(found.getErrorMessage()).isEqualTo("IllegalStateException");
    }

    @Test
    void sweep_abandonsCanceledInvitationWithoutSendingMail() {
        InvitationFixture fixture = createInvitationFixture("invitee@example.com", LocalDateTime.now());
        InvitationMail mail = saveMail(fixture.invitation(), fixture.invitee().getEmail());
        fixture.invitation().cancel(LocalDateTime.now());
        projectInvitationRepository.saveAndFlush(fixture.invitation());

        invitationMailSweeper.sweep();

        InvitationMail found = invitationMailRepository.findById(mail.getId()).orElseThrow();
        then(invitationMailClient).should(never()).send(any(InvitationMailContent.class));
        assertThat(found.getSendStatus()).isEqualTo(MailSendStatus.FAILED);
        assertThat(found.getErrorMessage()).isNotBlank();
        assertThat(found.getInviteLink()).isNull();
    }

    @Test
    void sweep_abandonsExpiredInvitationWithoutSendingMail() {
        InvitationFixture fixture = createInvitationFixture("invitee@example.com", LocalDateTime.now().minusHours(25));
        InvitationMail mail = saveMail(fixture.invitation(), fixture.invitee().getEmail());

        invitationMailSweeper.sweep();

        InvitationMail found = invitationMailRepository.findById(mail.getId()).orElseThrow();
        then(invitationMailClient).should(never()).send(any(InvitationMailContent.class));
        assertThat(found.getSendStatus()).isEqualTo(MailSendStatus.FAILED);
        assertThat(found.getInviteLink()).isNull();
    }

    @Test
    void sweep_recoversStaleRequestingMailAndSendsIt() {
        InvitationFixture fixture = createInvitationFixture("invitee@example.com", LocalDateTime.now());
        InvitationMail mail = saveMail(fixture.invitation(), fixture.invitee().getEmail());
        mail.beginAttempt(LocalDateTime.now().minusMinutes(6));
        invitationMailRepository.saveAndFlush(mail);
        new TransactionTemplate(transactionManager).executeWithoutResult(status -> entityManager
                .createNativeQuery("UPDATE project_invitation_mail SET updated_at = :updatedAt WHERE id = :id")
                .setParameter("updatedAt", LocalDateTime.now().minusMinutes(6))
                .setParameter("id", mail.getId())
                .executeUpdate());
        entityManager.clear();

        invitationMailSweeper.sweep();

        InvitationMail found = invitationMailRepository.findById(mail.getId()).orElseThrow();
        then(invitationMailClient).should().send(any(InvitationMailContent.class));
        assertThat(found.getSendStatus()).isEqualTo(MailSendStatus.SENT);
        assertThat(found.getAttemptCount()).isEqualTo(2);
    }

    @Test
    void sweep_continuesBatchWhenOneMailFails() {
        InvitationFixture failedFixture = createInvitationFixture("failed@example.com", LocalDateTime.now());
        InvitationFixture successfulFixture = createInvitationFixture("success@example.com", LocalDateTime.now());
        InvitationMail failedMail = saveMail(failedFixture.invitation(), failedFixture.invitee().getEmail());
        InvitationMail successfulMail = saveMail(successfulFixture.invitation(), successfulFixture.invitee().getEmail());
        doAnswer(invocation -> {
            InvitationMailContent content = invocation.getArgument(0);
            if (content.recipientEmail().equals("failed@example.com")) {
                throw new IllegalStateException("SMTP 연결 실패");
            }
            return null;
        }).when(invitationMailClient).send(any(InvitationMailContent.class));

        invitationMailSweeper.sweep();

        assertThat(invitationMailRepository.findById(failedMail.getId()).orElseThrow().getSendStatus())
                .isEqualTo(MailSendStatus.NOT_REQUESTED);
        assertThat(invitationMailRepository.findById(successfulMail.getId()).orElseThrow().getSendStatus())
                .isEqualTo(MailSendStatus.SENT);
    }

    @Test
    void sweep_skipsPoisonMailAndContinuesWithNextMail() {
        InvitationFixture poisonFixture = createInvitationFixture("poison@example.com", LocalDateTime.now());
        InvitationFixture normalFixture = createInvitationFixture("normal@example.com", LocalDateTime.now());
        ProjectInvitation poisonInvitation = ProjectInvitation.builder()
                .project(poisonFixture.project())
                .inviterMemberId(999_999)
                .inviteeMemberId(poisonFixture.invitee().getId())
                .tokenHash("poison-token")
                .lastInvitedAt(LocalDateTime.now())
                .build();
        projectInvitationRepository.delete(poisonFixture.invitation());
        poisonInvitation = projectInvitationRepository.saveAndFlush(poisonInvitation);
        InvitationMail poisonMail = saveMail(poisonInvitation, poisonFixture.invitee().getEmail());
        InvitationMail normalMail = saveMail(normalFixture.invitation(), normalFixture.invitee().getEmail());

        invitationMailSweeper.sweep();

        assertThat(invitationMailRepository.findById(poisonMail.getId()).orElseThrow().getSendStatus())
                .isEqualTo(MailSendStatus.NOT_REQUESTED);
        assertThat(invitationMailRepository.findById(normalMail.getId()).orElseThrow().getSendStatus())
                .isEqualTo(MailSendStatus.SENT);
    }

    @Test
    void sweep_doesNotTouchNonPendingMail() {
        InvitationFixture fixture = createInvitationFixture("invitee@example.com", LocalDateTime.now());
        InvitationMail mail = saveMail(fixture.invitation(), fixture.invitee().getEmail());
        mail.beginAttempt(LocalDateTime.now());
        mail.succeed();
        invitationMailRepository.saveAndFlush(mail);

        invitationMailSweeper.sweep();

        InvitationMail found = invitationMailRepository.findById(mail.getId()).orElseThrow();
        then(invitationMailClient).should(never()).send(any(InvitationMailContent.class));
        assertThat(found.getSendStatus()).isEqualTo(MailSendStatus.SENT);
    }

    private InvitationFixture createInvitationFixture(String inviteeEmail, LocalDateTime invitedAt) {
        Member owner = memberRepository.saveAndFlush(Member.builder()
                .email("owner-" + inviteeEmail)
                .name("소유자")
                .build());
        Member invitee = memberRepository.saveAndFlush(Member.builder()
                .email(inviteeEmail)
                .name("초대 대상")
                .build());
        Project project = Project.builder()
                .title("초대 테스트 프로젝트")
                .content("메일 발송 스위퍼 테스트입니다.")
                .build();
        project.addMember(ProjectMember.createMember(owner.getId(), ProjectRole.OWNER));
        project = projectRepository.saveAndFlush(project);
        ProjectInvitation invitation = projectInvitationRepository.saveAndFlush(ProjectInvitation.builder()
                .project(project)
                .inviterMemberId(owner.getId())
                .inviteeMemberId(invitee.getId())
                .tokenHash("token-" + inviteeEmail)
                .lastInvitedAt(invitedAt)
                .build());
        return new InvitationFixture(owner, invitee, project, invitation);
    }

    private InvitationMail saveMail(ProjectInvitation invitation, String recipientEmail) {
        return invitationMailRepository.saveAndFlush(InvitationMail.queue(
                invitation.getId(), recipientEmail, "https://projectree.site/invitations/token"
        ));
    }

    private record InvitationFixture(Member owner, Member invitee, Project project, ProjectInvitation invitation) {
    }
}
