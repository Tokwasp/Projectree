package com.ssafy.projectree.domain.project.entity;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ProjectMemberTest {

    @DisplayName("빌더로 생성하면 memberId와 role만 세팅되고 project는 비어 있다.")
    @Test
    void build_withoutProject() {
        // given & when
        ProjectMember projectMember = createMember(1, ProjectRole.MEMBER);

        // then
        assertThat(projectMember.getMemberId()).isEqualTo(1);
        assertThat(projectMember.getRole()).isEqualTo(ProjectRole.MEMBER);
        assertThat(projectMember.getProject()).isNull();
    }

    @DisplayName("assignProject를 호출하면 project가 세팅된다.")
    @Test
    void assignProject() {
        // given
        ProjectMember projectMember = createMember(1, ProjectRole.MEMBER);
        Project project = Project.builder()
                .title("포트폴리오 사이트")
                .content("React로 만든 개인 포트폴리오입니다.")
                .build();

        // when
        projectMember.assignProject(project);

        // then
        assertThat(projectMember.getProject()).isSameAs(project);
    }

    private ProjectMember createMember(int memberId, ProjectRole role) {
        return ProjectMember.builder()
                .memberId(memberId)
                .role(role)
                .build();
    }
}
