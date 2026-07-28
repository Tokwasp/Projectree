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
        project.addMember(1, ProjectRole.OWNER);

        // then
        assertThat(project.getProjectMembers()).hasSize(1)
                .first()
                .extracting("project", "memberId", "role")
                .containsExactly(project, 1, ProjectRole.OWNER);
    }

    @DisplayName("removeMember로 해당 memberId의 멤버만 목록에서 제거된다.")
    @Test
    void removeMember() {
        // given
        Project project = createProject("포트폴리오 사이트");
        project.addMember(1, ProjectRole.OWNER);
        project.addMember(2, ProjectRole.MEMBER);

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
        project.addMember(1, ProjectRole.OWNER);

        // when
        project.removeMember(999);

        // then
        assertThat(project.getProjectMembers()).hasSize(1);
    }

    @DisplayName("removeMember에 null을 넘겨도 예외 없이 아무것도 제거되지 않는다.")
    @Test
    void removeMember_null() {
        // given
        Project project = createProject("포트폴리오 사이트");
        project.addMember(1, ProjectRole.OWNER);

        // when
        project.removeMember(null);

        // then
        assertThat(project.getProjectMembers()).hasSize(1);
    }

    private Project createProject(String title) {
        return Project.builder()
                .title(title)
                .content("React로 만든 개인 포트폴리오입니다.")
                .build();
    }
}
