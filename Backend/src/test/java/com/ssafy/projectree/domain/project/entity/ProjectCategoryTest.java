package com.ssafy.projectree.domain.project.entity;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class ProjectCategoryTest {

    @DisplayName("createProjectCategory로 생성하면 categoryId만 세팅되고 project는 비어 있다.")
    @Test
    void createProjectCategory() {
        // given & when
        ProjectCategory projectCategory = ProjectCategory.createProjectCategory(1);

        // then
        assertThat(projectCategory.getCategoryId()).isEqualTo(1);
        assertThat(projectCategory.getProject()).isNull();
    }

    @DisplayName("assignProject를 호출하면 project가 세팅된다.")
    @Test
    void assignProject() {
        // given
        ProjectCategory projectCategory = ProjectCategory.createProjectCategory(1);
        Project project = Project.builder()
                .title("포트폴리오 사이트")
                .content("React로 만든 개인 포트폴리오입니다.")
                .build();

        // when
        projectCategory.assignProject(project);

        // then
        assertThat(projectCategory.getProject()).isSameAs(project);
    }
}
