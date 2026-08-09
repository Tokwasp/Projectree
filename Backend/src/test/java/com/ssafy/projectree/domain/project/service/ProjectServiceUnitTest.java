package com.ssafy.projectree.domain.project.service;

import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;

// 테스트 컨벤션의 기준인 Mockito 목 기반 서비스 테스트.
// ProjectServiceTest 는 아직 @SpringBootTest 기반이라 한 클래스에 두 방식을 섞을 수 없어 분리했다.
// ProjectServiceTest 가 목 기반으로 전환되면 이 클래스는 그쪽으로 합친다.
@ExtendWith(MockitoExtension.class)
class ProjectServiceUnitTest {

    private static final int PROJECT_ID = 1;
    private static final int OWNER_ID = 10;
    private static final int MEMBER_ID = 20;
    private static final Pageable PAGEABLE = PageRequest.of(0, 10);

    @InjectMocks
    private ProjectService projectService;

    @Mock
    private ProjectRepository projectRepository;

    @Mock
    private MemberRepository memberRepository;

    @Mock
    private ProjectDeletionService projectDeletionService;

    @DisplayName("MEMBER가 탈퇴하면 참여 멤버 목록에서 자신만 제거된다.")
    @Test
    void leaveProject() {
        // given
        Project project = createProjectWithOwnerAndMember();
        given(projectRepository.findByIdForUpdate(PROJECT_ID)).willReturn(Optional.of(project));

        // when
        projectService.leaveProject(PROJECT_ID, MEMBER_ID);

        // then
        assertThat(project.getProjectMembers())
                .extracting(ProjectMember::getMemberId)
                .containsExactly(OWNER_ID);
    }

    @DisplayName("참여하지 않은 회원이 탈퇴하려 하면 PROJECT_PARTICIPANT_NOT_FOUND 예외가 발생한다.")
    @Test
    void leaveProject_notParticipating() {
        // given
        Project project = createProjectWithOwnerAndMember();
        given(projectRepository.findByIdForUpdate(PROJECT_ID)).willReturn(Optional.of(project));

        // when // then
        assertThatThrownBy(() -> projectService.leaveProject(PROJECT_ID, 999))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND);
    }

    @DisplayName("존재하지 않는 프로젝트에서 탈퇴하려 하면 PROJECT_NOT_FOUND 예외가 발생한다.")
    @Test
    void leaveProject_projectNotFound() {
        // given
        given(projectRepository.findByIdForUpdate(999)).willReturn(Optional.empty());

        // when // then
        assertThatThrownBy(() -> projectService.leaveProject(999, MEMBER_ID))
                .isInstanceOf(CustomException.class)
                .extracting("errorCode")
                .isEqualTo(ProjectErrorCode.PROJECT_NOT_FOUND);
    }

    @DisplayName("OWNER가 탈퇴하면 공통 프로젝트 aggregate 삭제 서비스에 위임한다.")
    @Test
    void leaveProject_byOwner_delegatesAggregateDeletion() {
        // given
        Project project = createProjectWithOwnerAndMember();
        given(projectRepository.findByIdForUpdate(PROJECT_ID)).willReturn(Optional.of(project));

        // when
        projectService.leaveProject(PROJECT_ID, OWNER_ID);

        // then
        then(projectDeletionService).should().deleteProjectAggregate(PROJECT_ID);
    }

    @DisplayName("검색어의 LIKE 와일드카드 %는 리터럴로 이스케이프해서 Repository로 넘긴다.")
    @Test
    void getProjectList_escapesPercentInKeyword() {
        // given
        givenEmptyProjectPage();

        // when
        projectService.getProjectList(PAGEABLE, MEMBER_ID, "100%");

        // then
        thenSearchedWith("100!%");
    }

    @DisplayName("검색어의 LIKE 와일드카드 _는 리터럴로 이스케이프해서 Repository로 넘긴다.")
    @Test
    void getProjectList_escapesUnderscoreInKeyword() {
        // given
        givenEmptyProjectPage();

        // when
        projectService.getProjectList(PAGEABLE, MEMBER_ID, "snake_case");

        // then
        thenSearchedWith("snake!_case");
    }

    @DisplayName("검색어에 이스케이프 문자가 들어 있으면 이스케이프 문자 자체도 이스케이프한다.")
    @Test
    void getProjectList_escapesEscapeCharItself() {
        // given
        givenEmptyProjectPage();

        // when
        projectService.getProjectList(PAGEABLE, MEMBER_ID, "대박!");

        // then
        thenSearchedWith("대박!!");
    }

    @DisplayName("검색어 앞뒤 공백은 제거해서 Repository로 넘긴다.")
    @Test
    void getProjectList_trimsKeyword() {
        // given
        givenEmptyProjectPage();

        // when
        projectService.getProjectList(PAGEABLE, MEMBER_ID, "  포트폴리오  ");

        // then
        thenSearchedWith("포트폴리오");
    }

    @DisplayName("검색어가 공백뿐이면 null로 넘겨 필터 없이 전체를 조회한다.")
    @Test
    void getProjectList_withBlankKeyword() {
        // given
        givenEmptyProjectPage();

        // when
        projectService.getProjectList(PAGEABLE, MEMBER_ID, "   ");

        // then
        thenSearchedWith(null);
    }

    @DisplayName("검색어가 없으면 null로 넘겨 필터 없이 전체를 조회한다.")
    @Test
    void getProjectList_withNullKeyword() {
        // given
        givenEmptyProjectPage();

        // when
        projectService.getProjectList(PAGEABLE, MEMBER_ID, null);

        // then
        thenSearchedWith(null);
    }

    private void givenEmptyProjectPage() {
        given(projectRepository.findProjectItemsByMemberId(anyInt(), any(), any(Pageable.class)))
                .willReturn(Page.empty());
    }

    private void thenSearchedWith(String expectedKeyword) {
        then(projectRepository).should()
                .findProjectItemsByMemberId(eq(MEMBER_ID), eq(expectedKeyword), any(Pageable.class));
    }

    private Project createProjectWithOwnerAndMember() {
        Project project = Project.builder()
                .title("포트폴리오 사이트")
                .content("React로 만든 개인 포트폴리오입니다.")
                .build();
        project.addMember(ProjectMember.createMember(OWNER_ID, ProjectRole.OWNER));
        project.addMember(ProjectMember.createMember(MEMBER_ID, ProjectRole.MEMBER));
        return project;
    }
}
