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

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

// 테스트 컨벤션의 기준인 Mockito 목 기반 서비스 테스트.
// ProjectServiceTest 는 아직 @SpringBootTest 기반이라 한 클래스에 두 방식을 섞을 수 없어 분리했다.
// ProjectServiceTest 가 목 기반으로 전환되면 이 클래스는 그쪽으로 합친다.
@ExtendWith(MockitoExtension.class)
class ProjectServiceUnitTest {

    private static final int PROJECT_ID = 1;
    private static final int OWNER_ID = 10;
    private static final int MEMBER_ID = 20;

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

    @DisplayName("OWNER 탈퇴는 공통 프로젝트 aggregate 삭제 서비스를 사용한다.")
    @Test
    void leaveProject_byOwner_delegatesAggregateDeletion() {
        Project project = createProjectWithOwnerAndMember();
        given(projectRepository.findByIdForUpdate(PROJECT_ID)).willReturn(Optional.of(project));

        projectService.leaveProject(PROJECT_ID, OWNER_ID);

        verify(projectDeletionService).deleteProjectAggregate(PROJECT_ID);
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
