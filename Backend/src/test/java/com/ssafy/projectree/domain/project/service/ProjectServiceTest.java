package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProjectServiceTest extends IntegrationTestSupport {

    @Autowired
    private ProjectService projectService;

    @Autowired
    private MemberRepository memberRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @DisplayName("프로젝트를 생성하면 생성된 프로젝트의 id를 반환한다.")
    @Test
    void createProject() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        int projectId = projectService.createProject(request, member.getId());

        // then
        assertThat(projectId).isPositive();
    }

    @DisplayName("프로젝트를 생성하면 제목/설명/이미지 URL이 그대로 저장된다.")
    @Test
    void createProject_persistsFields() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request =
                createRequest("포트폴리오 사이트", "https://cdn.example.com/thumb.png");

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found)
                .extracting("title", "content", "photoUrl")
                .containsExactly(
                        "포트폴리오 사이트",
                        "React로 만든 개인 포트폴리오입니다.",
                        "https://cdn.example.com/thumb.png"
                );
    }

    @DisplayName("프로젝트를 생성하면 생성한 회원이 OWNER로 참여 멤버에 등록된다.")
    @Test
    void createProject_registersCreatorAsOwner() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getProjectMembers()).hasSize(1)
                .first()
                .extracting(ProjectMember::getMemberId, ProjectMember::getRole)
                .containsExactly(member.getId(), ProjectRole.OWNER);
    }

    @DisplayName("생성된 ProjectMember는 프로젝트와 양방향으로 연결된다.")
    @Test
    void createProject_linksProjectMemberToProject() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getProjectMembers().get(0).getProject().getId())
                .isEqualTo(projectId);
    }

    @DisplayName("photoUrl이 없어도 프로젝트를 생성할 수 있다.")
    @Test
    void createProject_withoutPhotoUrl() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getPhotoUrl()).isNull();
    }

    @DisplayName("존재하지 않는 회원 id로 프로젝트를 생성하면 MEMBER_NOT_FOUND 예외가 발생한다.")
    @Test
    void createProject_memberNotFound() {
        // given
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when // then
        assertThatThrownBy(() -> projectService.createProject(request, 999))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(CommonErrorCode.MEMBER_NOT_FOUND);
    }

    @DisplayName("존재하지 않는 회원 id로 프로젝트 생성에 실패하면 프로젝트가 저장되지 않는다.")
    @Test
    void createProject_memberNotFound_savesNothing() {
        // given
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null);

        // when
        assertThatThrownBy(() -> projectService.createProject(request, 999))
                .isInstanceOf(CustomException.class);

        // then
        assertThat(projectRepository.count()).isZero();
    }

    private void flushAndClear() {
        entityManager.flush();
        entityManager.clear();
    }

    private Member createMember(String email, String name) {
        return Member.builder()
                .email(email)
                .name(name)
                .build();
    }

    private ProjectCreateRequest createRequest(String title, String photoUrl) {
        return ProjectCreateRequest.builder()
                .title(title)
                .content("React로 만든 개인 포트폴리오입니다.")
                .photoUrl(photoUrl)
                .build();
    }
}
