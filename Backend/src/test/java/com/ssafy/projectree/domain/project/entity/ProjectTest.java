package com.ssafy.projectree.domain.project.entity;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ProjectTest {

    @DisplayName("빌더로 생성하면 projectMembers가 빈 리스트로 초기화된다.")
    @Test
    void build_initializesProjectMembers() {
        // given & when
        Project project = createProject("포트폴리오 사이트");

        // then
        assertThat(project.getProjectMembers()).isEmpty();
    }

    @DisplayName("addMember로 멤버를 추가하면 목록에 담기고 project/memberId/role이 세팅된다.")
    @Test
    void addMember() {
        // given
        Project project = createProject("포트폴리오 사이트");

        // when
        addMember(project, 1, ProjectRole.OWNER);

        // then
        assertThat(project.getProjectMembers()).hasSize(1)
                .first()
                .extracting("project", "memberId", "role")
                .containsExactly(project, 1, ProjectRole.OWNER);
    }

    @DisplayName("addMember는 넘겨받은 ProjectMember에 자신을 project로 주입한다.")
    @Test
    void addMember_assignsProject() {
        // given
        Project project = createProject("포트폴리오 사이트");
        ProjectMember projectMember = createMember(1, ProjectRole.OWNER);

        // when
        project.addMember(projectMember);

        // then
        assertThat(projectMember.getProject()).isSameAs(project);
    }

    @DisplayName("removeMember로 해당 memberId의 멤버만 목록에서 제거된다.")
    @Test
    void removeMember() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);
        addMember(project, 2, ProjectRole.MEMBER);

        // when
        project.removeMember(2);

        // then
        assertThat(project.getProjectMembers()).hasSize(1)
                .first()
                .extracting(ProjectMember::getMemberId)
                .isEqualTo(1);
    }

    @DisplayName("removeMember에 참여하지 않은 memberId를 넘기면 목록이 그대로 유지된다.")
    @Test
    void removeMember_notParticipating() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);

        // when
        project.removeMember(999);

        // then
        assertThat(project.getProjectMembers()).hasSize(1);
    }

    @DisplayName("isOwner는 해당 memberId가 OWNER로 참여 중이면 true를 반환한다.")
    @Test
    void isOwner() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);

        // when // then
        assertThat(project.isOwner(1)).isTrue();
    }

    @DisplayName("isOwner는 참여 중이지만 role이 OWNER가 아니면 false를 반환한다.")
    @Test
    void isOwner_withMemberRole() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.MEMBER);

        // when // then
        assertThat(project.isOwner(1)).isFalse();
    }

    @DisplayName("isOwner는 참여하지 않은 memberId면 false를 반환한다.")
    @Test
    void isOwner_notParticipating() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);

        // when // then
        assertThat(project.isOwner(999)).isFalse();
    }

    @DisplayName("isOwner는 참여 멤버가 없으면 false를 반환한다.")
    @Test
    void isOwner_withoutMembers() {
        // given
        Project project = createProject("포트폴리오 사이트");

        // when // then
        assertThat(project.isOwner(1)).isFalse();
    }

    @DisplayName("isOwner는 여러 멤버 중 OWNER인 멤버만 true로 판별한다.")
    @Test
    void isOwner_amongMultipleMembers() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.MEMBER);
        addMember(project, 2, ProjectRole.OWNER);
        addMember(project, 3, ProjectRole.MEMBER);

        // when // then
        assertThat(project.isOwner(2)).isTrue();
        assertThat(project.isOwner(1)).isFalse();
        assertThat(project.isOwner(3)).isFalse();
    }

    @DisplayName("isParticipant는 role이 OWNER여도 참여 중이면 true를 반환한다.")
    @Test
    void isParticipant_withOwnerRole() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);

        // when // then
        assertThat(project.isParticipant(1)).isTrue();
    }

    @DisplayName("isParticipant는 role이 MEMBER여도 참여 중이면 true를 반환한다.")
    @Test
    void isParticipant_withMemberRole() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.MEMBER);

        // when // then
        assertThat(project.isParticipant(1)).isTrue();
    }

    @DisplayName("isParticipant는 참여하지 않은 memberId면 false를 반환한다.")
    @Test
    void isParticipant_notParticipating() {
        // given
        Project project = createProject("포트폴리오 사이트");
        addMember(project, 1, ProjectRole.OWNER);
        addMember(project, 2, ProjectRole.MEMBER);

        // when // then
        assertThat(project.isParticipant(999)).isFalse();
    }

    private Project createProject(String title) {
        return Project.builder()
                .title(title)
                .content("React로 만든 개인 포트폴리오입니다.")
                .build();
    }

    private ProjectMember createMember(int memberId, ProjectRole role) {
        return ProjectMember.builder()
                .memberId(memberId)
                .role(role)
                .build();
    }

    private void addMember(Project project, int memberId, ProjectRole role) {
        project.addMember(createMember(memberId, role));
    }
}
