package com.ssafy.projectree.domain.project.entity;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ProjectMemberTest {

    @DisplayName("changeRole을 호출하면 역할이 변경된다.")
    @Test
    void changeRole() {
        // given
        ProjectMember projectMember = ProjectMember.builder()
                .memberId(1)
                .role(ProjectRole.MEMBER)
                .build();

        // when
        projectMember.changeRole(ProjectRole.OWNER);

        // then
        assertThat(projectMember.getRole()).isEqualTo(ProjectRole.OWNER);
    }
}
