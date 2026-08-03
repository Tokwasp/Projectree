package com.ssafy.projectree.domain.project.repository;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectInvitation;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.dao.DataIntegrityViolationException;

import java.time.LocalDateTime;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProjectInvitationRepositoryTest extends IntegrationTestSupport {

    private static final LocalDateTime INVITED_AT = LocalDateTime.of(2026, 7, 30, 10, 0);

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private ProjectInvitationRepository projectInvitationRepository;

    @DisplayName("프로젝트와 초대 대상 회원 id로 초대를 조회한다.")
    @Test
    void findByProjectIdAndInviteeMemberId() {
        // given
        Project project = projectRepository.saveAndFlush(createProject());
        ProjectInvitation invitation = projectInvitationRepository.saveAndFlush(
                createInvitation(project, 2, "token-hash")
        );

        // when
        var found = projectInvitationRepository.findByProjectIdAndInviteeMemberId(project.getId(), 2);
        var notFound = projectInvitationRepository.findByProjectIdAndInviteeMemberId(project.getId(), 999);

        // then
        assertThat(found).contains(invitation);
        assertThat(notFound).isEmpty();
    }

    @DisplayName("토큰 해시로 초대를 조회한다.")
    @Test
    void findByTokenHash() {
        // given
        Project project = projectRepository.saveAndFlush(createProject());
        ProjectInvitation invitation = projectInvitationRepository.saveAndFlush(
                createInvitation(project, 2, "token-hash")
        );

        // when
        var found = projectInvitationRepository.findByTokenHash("token-hash");

        // then
        assertThat(found).contains(invitation);
    }

    @DisplayName("락을 사용한 토큰 해시와 id 조회는 각각 해당 초대를 반환한다.")
    @Test
    void findWithLock() {
        // given
        Project project = projectRepository.saveAndFlush(createProject());
        ProjectInvitation invitation = projectInvitationRepository.saveAndFlush(
                createInvitation(project, 2, "token-hash")
        );

        // when
        var foundByTokenHash = projectInvitationRepository.findWithLockByTokenHash("token-hash");
        var foundById = projectInvitationRepository.findWithLockById(invitation.getId());

        // then
        assertThat(foundByTokenHash).contains(invitation);
        assertThat(foundById).contains(invitation);
    }

    @DisplayName("같은 프로젝트에 같은 회원을 두 번 초대하면 유니크 제약 위반으로 저장에 실패한다.")
    @Test
    void save_duplicateProjectAndInvitee_throwsException() {
        // given
        Project project = projectRepository.saveAndFlush(createProject());
        projectInvitationRepository.saveAndFlush(createInvitation(project, 2, "first-token-hash"));

        // when & then
        assertThatThrownBy(() -> projectInvitationRepository.saveAndFlush(
                createInvitation(project, 2, "second-token-hash")
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    @DisplayName("같은 토큰 해시로 두 초대를 저장하면 유니크 제약 위반으로 저장에 실패한다.")
    @Test
    void save_duplicateTokenHash_throwsException() {
        // given
        Project project = projectRepository.saveAndFlush(createProject());
        projectInvitationRepository.saveAndFlush(createInvitation(project, 2, "duplicated-token-hash"));

        // when & then
        assertThatThrownBy(() -> projectInvitationRepository.saveAndFlush(
                createInvitation(project, 3, "duplicated-token-hash")
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    private Project createProject() {
        return Project.builder()
                .title("프로젝트 초대")
                .content("프로젝트 초대 Repository 테스트입니다.")
                .build();
    }

    private ProjectInvitation createInvitation(Project project, int inviteeMemberId, String tokenHash) {
        return ProjectInvitation.builder()
                .project(project)
                .inviterMemberId(1)
                .inviteeMemberId(inviteeMemberId)
                .tokenHash(tokenHash)
                .lastInvitedAt(INVITED_AT)
                .build();
    }
}
