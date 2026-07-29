package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectCategory;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;

import java.util.List;

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
                .isEqualTo(ProjectErrorCode.MEMBER_NOT_FOUND);
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

    @DisplayName("프로젝트를 생성하면 요청한 카테고리가 모두 저장된다.")
    @Test
    void createProject_persistsCategories() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null, List.of(1, 2, 5));

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getProjectCategories())
                .extracting(ProjectCategory::getCategoryId)
                .containsExactlyInAnyOrder(1, 2, 5);
    }

    @DisplayName("카테고리를 하나만 선택해도 프로젝트를 생성할 수 있다.")
    @Test
    void createProject_withSingleCategory() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null, List.of(3));

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getProjectCategories()).hasSize(1)
                .first()
                .extracting(ProjectCategory::getCategoryId)
                .isEqualTo(3);
    }

    @DisplayName("1부터 6까지 모든 카테고리를 선택할 수 있다.")
    @Test
    void createProject_withAllCategories() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request =
                createRequest("포트폴리오 사이트", null, List.of(1, 2, 3, 4, 5, 6));

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getProjectCategories())
                .extracting(ProjectCategory::getCategoryId)
                .containsExactlyInAnyOrder(1, 2, 3, 4, 5, 6);
    }

    @DisplayName("같은 카테고리를 여러 번 보내면 중복이 제거되어 한 번만 저장된다.")
    @Test
    void createProject_deduplicatesCategories() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request =
                createRequest("포트폴리오 사이트", null, List.of(1, 1, 2, 2, 2));

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getProjectCategories())
                .extracting(ProjectCategory::getCategoryId)
                .containsExactlyInAnyOrder(1, 2);
    }

    @DisplayName("저장된 ProjectCategory는 프로젝트와 양방향으로 연결된다.")
    @Test
    void createProject_linksProjectCategoryToProject() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request = createRequest("포트폴리오 사이트", null, List.of(1));

        // when
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // then
        Project found = projectRepository.findById(projectId).orElseThrow();
        assertThat(found.getProjectCategories().get(0).getProject().getId())
                .isEqualTo(projectId);
    }

    @DisplayName("카테고리 id가 1~6 범위를 벗어나면 INVALID_REQUEST 예외가 발생한다.")
    @ParameterizedTest
    @ValueSource(ints = {-1, 0, 7, 100, Integer.MAX_VALUE, Integer.MIN_VALUE})
    void createProject_categoryIdOutOfRange(int categoryId) {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request =
                createRequest("포트폴리오 사이트", null, List.of(categoryId));

        // when // then
        assertThatThrownBy(() -> projectService.createProject(request, member.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.INVALID_REQUEST);
    }

    @DisplayName("유효한 카테고리와 유효하지 않은 카테고리가 섞여 있으면 예외가 발생한다.")
    @Test
    void createProject_withPartiallyInvalidCategories() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request =
                createRequest("포트폴리오 사이트", null, List.of(1, 2, 99));

        // when // then
        assertThatThrownBy(() -> projectService.createProject(request, member.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.INVALID_REQUEST);
    }

    @DisplayName("유효하지 않은 카테고리로 생성에 실패하면 프로젝트가 저장되지 않는다.")
    @Test
    void createProject_invalidCategory_savesNothing() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request =
                createRequest("포트폴리오 사이트", null, List.of(1, 99));

        // when
        assertThatThrownBy(() -> projectService.createProject(request, member.getId()))
                .isInstanceOf(CustomException.class);
        flushAndClear();

        // then
        assertThat(projectRepository.count()).isZero();
    }

    @DisplayName("회원 검증이 카테고리 검증보다 먼저 수행된다.")
    @Test
    void createProject_validatesMemberBeforeCategory() {
        // given
        ProjectCreateRequest request =
                createRequest("포트폴리오 사이트", null, List.of(99));

        // when // then
        assertThatThrownBy(() -> projectService.createProject(request, 999))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.MEMBER_NOT_FOUND);
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
        return createRequest(title, photoUrl, List.of(1));
    }

    private ProjectCreateRequest createRequest(String title, String photoUrl, List<Integer> categoryIds) {
        return ProjectCreateRequest.builder()
                .title(title)
                .content("React로 만든 개인 포트폴리오입니다.")
                .photoUrl(photoUrl)
                .categoryIds(categoryIds)
                .build();
    }
}
