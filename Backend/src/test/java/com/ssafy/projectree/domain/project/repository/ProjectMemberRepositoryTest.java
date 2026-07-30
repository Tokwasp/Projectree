package com.ssafy.projectree.domain.project.repository;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import static org.assertj.core.api.Assertions.assertThat;

class ProjectMemberRepositoryTest extends IntegrationTestSupport {

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private ProjectMemberRepository projectMemberRepository;

    @DisplayName("프로젝트에 참여한 회원인지 확인한다.")
    @Test
    void existsByProjectIdAndMemberId() {
        // given
        Project project = createProject();
        project.addMember(ProjectMember.createMember(1, ProjectRole.OWNER));
        Project savedProject = projectRepository.saveAndFlush(project);

        // when
        boolean memberExists = projectMemberRepository.existsByProjectIdAndMemberId(savedProject.getId(), 1);
        boolean nonMemberExists = projectMemberRepository.existsByProjectIdAndMemberId(savedProject.getId(), 999);

        // then
        assertThat(memberExists).isTrue();
        assertThat(nonMemberExists).isFalse();
    }

    @DisplayName("프로젝트 참여 회원의 OWNER 권한 여부를 확인한다.")
    @Test
    void existsByProjectIdAndMemberIdAndRole() {
        // given
        Project project = createProject();
        project.addMember(ProjectMember.createMember(1, ProjectRole.OWNER));
        project.addMember(ProjectMember.createMember(2, ProjectRole.MEMBER));
        Project savedProject = projectRepository.saveAndFlush(project);

        // when
        boolean ownerExists = projectMemberRepository.existsByProjectIdAndMemberIdAndRole(
                savedProject.getId(), 1, ProjectRole.OWNER
        );
        boolean memberIsOwner = projectMemberRepository.existsByProjectIdAndMemberIdAndRole(
                savedProject.getId(), 2, ProjectRole.OWNER
        );

        // then
        assertThat(ownerExists).isTrue();
        assertThat(memberIsOwner).isFalse();
    }

    @DisplayName("다른 프로젝트에 속한 회원은 멤버나 OWNER로 조회되지 않는다.")
    @Test
    void existsByProjectIdAndMemberId_differentProject() {
        // given
        Project firstProject = createProject();
        firstProject.addMember(ProjectMember.createMember(1, ProjectRole.OWNER));
        projectRepository.saveAndFlush(firstProject);
        Project secondProject = projectRepository.saveAndFlush(createProject());

        // when
        boolean memberExists = projectMemberRepository.existsByProjectIdAndMemberId(secondProject.getId(), 1);
        boolean ownerExists = projectMemberRepository.existsByProjectIdAndMemberIdAndRole(
                secondProject.getId(), 1, ProjectRole.OWNER
        );

        // then
        assertThat(memberExists).isFalse();
        assertThat(ownerExists).isFalse();
    }

    private Project createProject() {
        return Project.builder()
                .title("프로젝트 초대")
                .content("프로젝트 멤버 Repository 테스트입니다.")
                .build();
    }
}
