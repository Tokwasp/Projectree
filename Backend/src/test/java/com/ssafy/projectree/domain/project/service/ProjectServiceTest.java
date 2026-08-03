package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.IntegrationTestSupport;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse;
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
import static org.assertj.core.api.Assertions.tuple;

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
                .isEqualTo(ProjectErrorCode.INVALID_CATEGORY);
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
                .isEqualTo(ProjectErrorCode.INVALID_CATEGORY);
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

    @DisplayName("OWNER는 자신의 프로젝트를 삭제할 수 있다.")
    @Test
    void deleteProject() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        int projectId = createProjectOwnedBy(member);

        // when
        projectService.deleteProject(projectId, member.getId());
        flushAndClear();

        // then
        assertThat(projectRepository.findById(projectId)).isEmpty();
    }

    @DisplayName("프로젝트를 삭제하면 참여 멤버와 카테고리도 함께 삭제된다.")
    @Test
    void deleteProject_cascadesChildren() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        ProjectCreateRequest request =
                createRequest("포트폴리오 사이트", null, List.of(1, 2, 3));
        int projectId = projectService.createProject(request, member.getId());
        flushAndClear();

        // when
        projectService.deleteProject(projectId, member.getId());
        flushAndClear();

        // then
        assertThat(countProjectMembers()).isZero();
        assertThat(countProjectCategories()).isZero();
    }

    @DisplayName("OWNER가 아닌 참여 멤버가 삭제하려 하면 PROJECT_DELETE_FORBIDDEN 예외가 발생한다.")
    @Test
    void deleteProject_withMemberRole() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김싸피"));
        Member participant = memberRepository.save(createMember("member@gmail.com", "이싸피"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, participant);

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(projectId, participant.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_FORBIDDEN);
    }

    @DisplayName("프로젝트에 참여하지 않은 회원이 삭제하려 하면 PROJECT_DELETE_FORBIDDEN 예외가 발생한다.")
    @Test
    void deleteProject_notParticipating() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김싸피"));
        Member stranger = memberRepository.save(createMember("stranger@gmail.com", "박싸피"));
        int projectId = createProjectOwnedBy(owner);

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(projectId, stranger.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_DELETE_FORBIDDEN);
    }

    @DisplayName("삭제 권한이 없어 실패하면 프로젝트와 자식 행이 그대로 남는다.")
    @Test
    void deleteProject_forbidden_deletesNothing() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김싸피"));
        Member stranger = memberRepository.save(createMember("stranger@gmail.com", "박싸피"));
        int projectId = createProjectOwnedBy(owner);

        // when
        assertThatThrownBy(() -> projectService.deleteProject(projectId, stranger.getId()))
                .isInstanceOf(CustomException.class);
        flushAndClear();

        // then
        assertThat(projectRepository.findById(projectId)).isPresent();
        assertThat(countProjectMembers()).isEqualTo(1L);
        assertThat(countProjectCategories()).isEqualTo(1L);
    }

    @DisplayName("존재하지 않는 프로젝트를 삭제하려 하면 PROJECT_NOT_FOUND 예외가 발생한다.")
    @Test
    void deleteProject_projectNotFound() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(999, member.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("프로젝트 존재 검증이 권한 검증보다 먼저 수행된다.")
    @Test
    void deleteProject_validatesProjectBeforePermission() {
        // given
        Member stranger = memberRepository.save(createMember("stranger@gmail.com", "박싸피"));

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(999, stranger.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("같은 프로젝트를 두 번 삭제하면 두 번째는 PROJECT_NOT_FOUND 예외가 발생한다.")
    @Test
    void deleteProject_twice() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        int projectId = createProjectOwnedBy(member);
        projectService.deleteProject(projectId, member.getId());
        flushAndClear();

        // when // then
        assertThatThrownBy(() -> projectService.deleteProject(projectId, member.getId()))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("한 프로젝트를 삭제해도 다른 프로젝트는 남는다.")
    @Test
    void deleteProject_doesNotAffectOtherProjects() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));
        int target = createProjectOwnedBy(member);
        int other = projectService.createProject(
                createRequest("스터디 관리 앱", null), member.getId());
        flushAndClear();

        // when
        projectService.deleteProject(target, member.getId());
        flushAndClear();

        // then
        assertThat(projectRepository.findById(target)).isEmpty();
        assertThat(projectRepository.findById(other)).isPresent();
    }

    @DisplayName("프로젝트 참여자가 팀원 목록을 조회하면 참여자 전원이 회원 정보와 함께 반환된다.")
    @Test
    void getProjectMembers() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        // when
        List<ProjectMemberResponse> result =
                projectService.getProjectMembers(projectId, member.getId());

        // then
        assertThat(result)
                .extracting("memberId", "name", "email", "role")
                .containsExactly(
                        tuple(owner.getId(), "김오너", "owner@gmail.com", ProjectRole.OWNER),
                        tuple(member.getId(), "이멤버", "member@gmail.com", ProjectRole.MEMBER)
                );
    }

    @DisplayName("OWNER 도 자기 프로젝트의 팀원 목록을 조회할 수 있다.")
    @Test
    void getProjectMembers_byOwner() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        int projectId = createProjectOwnedBy(owner);

        // when
        List<ProjectMemberResponse> result =
                projectService.getProjectMembers(projectId, owner.getId());

        // then
        assertThat(result).hasSize(1);
        assertThat(result.getFirst().getRole()).isEqualTo(ProjectRole.OWNER);
    }

    @DisplayName("참여하지 않은 회원이 팀원 목록을 조회하면 예외가 발생한다.")
    @Test
    void getProjectMembers_notParticipant() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member outsider = memberRepository.save(createMember("outsider@gmail.com", "남"));
        int projectId = createProjectOwnedBy(owner);

        // when // then
        assertThatThrownBy(() -> projectService.getProjectMembers(projectId, outsider.getId()))
                .isInstanceOf(CustomException.class)
                .hasMessage(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND.getMessage());
    }

    @DisplayName("존재하지 않는 프로젝트의 팀원 목록을 조회하면 예외가 발생한다.")
    @Test
    void getProjectMembers_projectNotFound() {
        // given
        Member member = memberRepository.save(createMember("ssafy@gmail.com", "김싸피"));

        // when // then
        assertThatThrownBy(() -> projectService.getProjectMembers(999_999, member.getId()))
                .isInstanceOf(CustomException.class)
                .hasMessage(ProjectErrorCode.PROJECT_NOT_FOUND.getMessage());
    }

    @DisplayName("프로젝트 존재 검증이 참여자 검증보다 먼저 수행된다.")
    @Test
    void getProjectMembers_validatesProjectBeforeParticipant() {
        // given
        // 프로젝트도 없고 참여자도 아닌 상황에서 어떤 예외가 나오는지로 검증 순서를 확인한다
        Member outsider = memberRepository.save(createMember("outsider@gmail.com", "남"));

        // when // then
        assertThatThrownBy(() -> projectService.getProjectMembers(999_999, outsider.getId()))
                .isInstanceOf(CustomException.class)
                .hasMessage(ProjectErrorCode.PROJECT_NOT_FOUND.getMessage());
    }

    @DisplayName("다른 프로젝트의 팀원은 목록에 포함되지 않는다.")
    @Test
    void getProjectMembers_excludesOtherProjectMembers() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member outsider = memberRepository.save(createMember("outsider@gmail.com", "남"));
        int target = createProjectOwnedBy(owner);
        int other = projectService.createProject(
                createRequest("스터디 관리 앱", null), outsider.getId());
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectService.getProjectMembers(target, owner.getId());

        // then
        assertThat(other).isNotEqualTo(target);
        assertThat(result)
                .extracting("name")
                .containsExactly("김오너");
    }

    @DisplayName("탈퇴한 회원은 팀원 목록에서 빠진다.")
    @Test
    void getProjectMembers_afterLeave() {
        // given
        Member owner = memberRepository.save(createMember("owner@gmail.com", "김오너"));
        Member member = memberRepository.save(createMember("member@gmail.com", "이멤버"));
        int projectId = createProjectOwnedBy(owner);
        joinAsMember(projectId, member);

        projectService.leaveProject(projectId, member.getId());
        flushAndClear();

        // when
        List<ProjectMemberResponse> result =
                projectService.getProjectMembers(projectId, owner.getId());

        // then
        assertThat(result)
                .extracting("name")
                .containsExactly("김오너");
    }

    private int createProjectOwnedBy(Member owner) {
        int projectId = projectService.createProject(
                createRequest("포트폴리오 사이트", null), owner.getId());
        flushAndClear();
        return projectId;
    }

    private void joinAsMember(int projectId, Member member) {
        Project project = projectRepository.findById(projectId).orElseThrow();
        project.addMember(ProjectMember.createMember(member.getId(), ProjectRole.MEMBER));
        flushAndClear();
    }

    private Long countProjectMembers() {
        return count("select count(*) from project_member");
    }

    private Long countProjectCategories() {
        return count("select count(*) from project_category");
    }

    private Long count(String sql) {
        Number count = (Number) entityManager.createNativeQuery(sql).getSingleResult();
        return count.longValue();
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
