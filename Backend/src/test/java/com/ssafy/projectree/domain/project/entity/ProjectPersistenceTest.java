package com.ssafy.projectree.domain.project.entity;

import com.ssafy.projectree.global.config.JpaAuditingConfig;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jpa.test.autoconfigure.TestEntityManager;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import java.sql.SQLIntegrityConstraintViolationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(JpaAuditingConfig.class)
@DataJpaTest
class ProjectPersistenceTest {

    @Autowired
    private TestEntityManager em;

    @DisplayName("프로젝트를 저장하면 cascade로 참여 멤버도 함께 저장된다.")
    @Test
    void save_cascadesProjectMembers() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);

        // when
        int projectId = em.persistFlushFind(project).getId();
        em.clear();

        // then
        Project found = em.find(Project.class, projectId);
        assertThat(found.getProjectMembers()).hasSize(1)
                .first()
                .extracting(ProjectMember::getMemberId, ProjectMember::getRole)
                .containsExactly(1, ProjectRole.OWNER);
    }

    @DisplayName("role은 ORDINAL이 아닌 문자열로 저장된다.")
    @Test
    void save_persistsRoleAsString() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);
        em.persistAndFlush(project);
        em.clear();

        // when
        Object role = em.getEntityManager()
                .createNativeQuery("select role from project_member")
                .getSingleResult();

        // then
        assertThat(role).isEqualTo("OWNER");
    }

    @DisplayName("BaseEntity 상속으로 createdAt과 updatedAt이 자동으로 채워진다.")
    @Test
    void save_fillsAuditingColumns() {
        // given
        Project project = createProject("포트폴리오 사이트");

        // when
        Project saved = em.persistFlushFind(project);

        // then
        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getUpdatedAt()).isNotNull();
    }

    @DisplayName("removeMember 후 flush하면 orphanRemoval로 project_member 행이 삭제된다.")
    @Test
    void removeMember_deletesRow() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);
        addMember(project, 2, ProjectRole.MEMBER);
        em.persistAndFlush(project);

        // when
        project.removeMember(2);
        em.flush();
        em.clear();

        // then
        assertThat(countProjectMembers()).isEqualTo(1L);
    }

    @DisplayName("같은 프로젝트에 같은 멤버를 두 번 추가하면 유니크 제약 위반으로 저장에 실패한다.")
    @Test
    void addMember_duplicated() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);
        addMember(project, 1, ProjectRole.MEMBER);

        // when & then
        assertThatThrownBy(() -> em.persistAndFlush(project))
                .rootCause()
                .isInstanceOf(SQLIntegrityConstraintViolationException.class);
    }

    @DisplayName("서로 다른 프로젝트에는 같은 멤버가 참여할 수 있다.")
    @Test
    void addMember_sameMemberAcrossProjects() {
        // given
        Project first = createProject("포트폴리오 사이트");
        addMember(first, 1, ProjectRole.OWNER);
        Project second = createProject("스터디 관리 앱");
        addMember(second, 1, ProjectRole.MEMBER);

        // when
        em.persistAndFlush(first);
        em.persistAndFlush(second);
        em.clear();

        // then
        assertThat(countProjectMembers()).isEqualTo(2L);
    }

    private Long countProjectMembers() {
        Number count = (Number) em.getEntityManager()
                .createNativeQuery("select count(*) from project_member")
                .getSingleResult();
        return count.longValue();
    }

    private Project createProject(String title) {
        return Project.builder()
                .title(title)
                .content("React로 만든 개인 포트폴리오입니다.")
                .build();
    }

    private void addMember(Project project, int memberId, ProjectRole role) {
        project.addMember(
                ProjectMember.builder()
                        .memberId(memberId)
                        .role(role)
                        .build()
        );
    }
}
