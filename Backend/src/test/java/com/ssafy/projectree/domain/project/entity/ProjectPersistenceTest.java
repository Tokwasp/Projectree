package com.ssafy.projectree.domain.project.entity;

import com.ssafy.projectree.global.config.JpaAuditingConfig;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.boot.jpa.test.autoconfigure.TestEntityManager;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import java.sql.SQLIntegrityConstraintViolationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(JpaAuditingConfig.class)
// 기본값(Replace.ANY)이면 application-test.yaml의 H2(MODE=MySQL) 대신 순수 H2로 교체되어
// data.sql의 MySQL 문법(INSERT IGNORE)이 깨진다.
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
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

    @DisplayName("프로젝트를 저장하면 cascade로 카테고리도 함께 저장된다.")
    @Test
    void save_cascadesProjectCategories() {
        // given
        Project project = createProject("포트폴리오 사이트");
        project.addCategory(ProjectCategory.createProjectCategory(1));
        project.addCategory(ProjectCategory.createProjectCategory(2));

        // when
        int projectId = em.persistFlushFind(project).getId();
        em.clear();

        // then
        Project found = em.find(Project.class, projectId);
        assertThat(found.getProjectCategories())
                .extracting(ProjectCategory::getCategoryId)
                .containsExactlyInAnyOrder(1, 2);
    }

    @DisplayName("저장된 ProjectCategory는 project_id로 프로젝트를 참조한다.")
    @Test
    void save_linksProjectCategoryToProject() {
        // given
        Project project = createProject("포트폴리오 사이트");
        project.addCategory(ProjectCategory.createProjectCategory(1));
        int projectId = em.persistFlushFind(project).getId();
        em.clear();

        // when
        Object storedProjectId = em.getEntityManager()
                .createNativeQuery("select project_id from project_category")
                .getSingleResult();

        // then
        assertThat(((Number) storedProjectId).intValue()).isEqualTo(projectId);
    }

    @DisplayName("같은 프로젝트에 같은 카테고리를 두 번 추가하면 유니크 제약 위반으로 저장에 실패한다.")
    @Test
    void addCategory_duplicated() {
        // given
        Project project = createProject("포트폴리오 사이트");
        project.addCategory(ProjectCategory.createProjectCategory(1));
        project.addCategory(ProjectCategory.createProjectCategory(1));

        // when & then
        assertThatThrownBy(() -> em.persistAndFlush(project))
                .rootCause()
                .isInstanceOf(SQLIntegrityConstraintViolationException.class);
    }

    @DisplayName("서로 다른 프로젝트는 같은 카테고리를 가질 수 있다.")
    @Test
    void addCategory_sameCategoryAcrossProjects() {
        // given
        Project first = createProject("포트폴리오 사이트");
        first.addCategory(ProjectCategory.createProjectCategory(1));
        Project second = createProject("스터디 관리 앱");
        second.addCategory(ProjectCategory.createProjectCategory(1));

        // when
        em.persistAndFlush(first);
        em.persistAndFlush(second);
        em.clear();

        // then
        assertThat(countProjectCategories()).isEqualTo(2L);
    }

    @DisplayName("ProjectCategory도 BaseEntity 상속으로 createdAt과 updatedAt이 자동으로 채워진다.")
    @Test
    void save_fillsProjectCategoryAuditingColumns() {
        // given
        Project project = createProject("포트폴리오 사이트");
        ProjectCategory projectCategory = ProjectCategory.createProjectCategory(1);
        project.addCategory(projectCategory);

        // when
        em.persistAndFlush(project);

        // then
        assertThat(projectCategory.getCreatedAt()).isNotNull();
        assertThat(projectCategory.getUpdatedAt()).isNotNull();
    }

    @DisplayName("카테고리 없이도 프로젝트만 저장할 수 있다.")
    @Test
    void save_withoutCategories() {
        // given
        Project project = createProject("포트폴리오 사이트");

        // when
        em.persistAndFlush(project);
        em.clear();

        // then
        assertThat(countProjectCategories()).isZero();
    }

    @DisplayName("프로젝트를 삭제하면 cascade로 project_member 행도 함께 삭제된다.")
    @Test
    void delete_cascadesProjectMembers() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);
        addMember(project, 2, ProjectRole.MEMBER);
        em.persistAndFlush(project);

        // when
        em.getEntityManager().remove(project);
        em.flush();
        em.clear();

        // then
        assertThat(countProjectMembers()).isZero();
    }

    @DisplayName("프로젝트를 삭제하면 cascade로 project_category 행도 함께 삭제된다.")
    @Test
    void delete_cascadesProjectCategories() {
        // given
        Project project = createProject("포트폴리오 사이트");
        project.addCategory(ProjectCategory.createProjectCategory(1));
        project.addCategory(ProjectCategory.createProjectCategory(2));
        em.persistAndFlush(project);

        // when
        em.getEntityManager().remove(project);
        em.flush();
        em.clear();

        // then
        assertThat(countProjectCategories()).isZero();
    }

    @DisplayName("프로젝트를 삭제하면 project 행 자체도 삭제된다.")
    @Test
    void delete_removesProjectRow() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);
        project.addCategory(ProjectCategory.createProjectCategory(1));
        em.persistAndFlush(project);
        int projectId = project.getId();

        // when
        em.getEntityManager().remove(project);
        em.flush();
        em.clear();

        // then
        assertThat(em.find(Project.class, projectId)).isNull();
    }

    @DisplayName("한 프로젝트를 삭제해도 다른 프로젝트의 멤버와 카테고리는 남는다.")
    @Test
    void delete_doesNotAffectOtherProjects() {
        // given
        Project target = createProject("포트폴리오 사이트");
        addMember(target, 1, ProjectRole.OWNER);
        target.addCategory(ProjectCategory.createProjectCategory(1));
        Project other = createProject("스터디 관리 앱");
        addMember(other, 1, ProjectRole.OWNER);
        other.addCategory(ProjectCategory.createProjectCategory(1));
        em.persistAndFlush(target);
        em.persistAndFlush(other);

        // when
        em.getEntityManager().remove(target);
        em.flush();
        em.clear();

        // then
        assertThat(countProjectMembers()).isEqualTo(1L);
        assertThat(countProjectCategories()).isEqualTo(1L);
    }

    private Long countProjectCategories() {
        Number count = (Number) em.getEntityManager()
                .createNativeQuery("select count(*) from project_category")
                .getSingleResult();
        return count.longValue();
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
