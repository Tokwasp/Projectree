package com.ssafy.projectree.domain.meeting.entity;

import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingTest {

    @DisplayName("Meeting을 생성하면 프로젝트와 roomName을 저장하고 분석 상태를 초기화한다.")
    @Test
    void createsMeeting() {
        Project project = createProject();
        ProjectMember creator = project.getProjectMembers().get(0);

        Meeting meeting = Meeting.create(
                project, creator, "550e8400-e29b-41d4-a716-446655440000"
        );

        assertThat(meeting.getProject()).isSameAs(project);
        assertThat(meeting.getCreatorMemberId()).isEqualTo(creator.getMemberId());
        assertThat(meeting.getRoomName()).isEqualTo("550e8400-e29b-41d4-a716-446655440000");
        assertThat(meeting.isGenerateSummary()).isFalse();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.NOT_REQUESTED);
        assertThat(meeting.isGenerateNodes()).isFalse();
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.NOT_REQUESTED);
        assertThat(meeting.isAnalysisRequestConfirmed()).isFalse();
    }

    @DisplayName("분석 옵션 조합에 따라 SUMMARY와 NODES 상태를 독립적으로 확정한다.")
    @ParameterizedTest
    @CsvSource({
            "true, true, PROCESSING, PROCESSING",
            "true, false, PROCESSING, SKIPPED",
            "false, true, SKIPPED, PROCESSING",
            "false, false, SKIPPED, SKIPPED"
    })
    void confirmAnalysisOptions(
            boolean generateSummary,
            boolean generateNodes,
            AnalysisTaskStatus expectedSummaryStatus,
            AnalysisTaskStatus expectedNodeStatus
    ) {
        Meeting meeting = createMeeting();

        meeting.confirmAnalysisOptions(generateSummary, generateNodes);

        assertThat(meeting.isGenerateSummary()).isEqualTo(generateSummary);
        assertThat(meeting.getSummaryStatus()).isEqualTo(expectedSummaryStatus);
        assertThat(meeting.isGenerateNodes()).isEqualTo(generateNodes);
        assertThat(meeting.getNodeStatus()).isEqualTo(expectedNodeStatus);
        assertThat(meeting.isAnalysisRequestConfirmed()).isTrue();
    }

    @DisplayName("분석 옵션은 한 번만 확정할 수 있고 두 번째 시도는 기존 값을 변경하지 않는다.")
    @Test
    void cannotConfirmAnalysisOptionsTwice() {
        Meeting meeting = createMeeting();
        meeting.confirmAnalysisOptions(true, false);

        assertThatThrownBy(() -> meeting.confirmAnalysisOptions(false, true))
                .isInstanceOf(IllegalStateException.class);
        assertThat(meeting.isGenerateSummary()).isTrue();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(meeting.isGenerateNodes()).isFalse();
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.SKIPPED);
    }

    @DisplayName("요약 성공은 PROCESSING 요약만 SUCCEEDED로 변경한다.")
    @Test
    void markSummarySucceeded() {
        Meeting meeting = createMeeting();
        meeting.confirmAnalysisOptions(true, true);

        meeting.markSummarySucceeded();

        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.SUCCEEDED);
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
    }

    @DisplayName("요약 실패는 PROCESSING 요약만 FAILED로 변경한다.")
    @Test
    void markSummaryFailed() {
        Meeting meeting = createMeeting();
        meeting.confirmAnalysisOptions(true, true);

        meeting.markSummaryFailed();

        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.FAILED);
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
    }

    @DisplayName("노드 성공은 PROCESSING 노드만 SUCCEEDED로 변경한다.")
    @Test
    void markNodesSucceeded() {
        Meeting meeting = createMeeting();
        meeting.confirmAnalysisOptions(true, true);

        meeting.markNodesSucceeded();

        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.SUCCEEDED);
    }

    @DisplayName("노드 실패는 PROCESSING 노드만 FAILED로 변경한다.")
    @Test
    void markNodesFailed() {
        Meeting meeting = createMeeting();
        meeting.confirmAnalysisOptions(true, true);

        meeting.markNodesFailed();

        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.FAILED);
    }

    @DisplayName("NOT_REQUESTED 상태에서는 성공 또는 실패로 전이할 수 없다.")
    @Test
    void cannotCompleteNotRequestedTasks() {
        Meeting meeting = createMeeting();

        assertThatThrownBy(meeting::markSummarySucceeded).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(meeting::markSummaryFailed).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(meeting::markNodesSucceeded).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(meeting::markNodesFailed).isInstanceOf(IllegalStateException.class);
    }

    @DisplayName("SKIPPED 상태에서는 성공 또는 실패로 전이할 수 없다.")
    @Test
    void cannotCompleteSkippedTasks() {
        Meeting meeting = createMeeting();
        meeting.confirmAnalysisOptions(false, false);

        assertThatThrownBy(meeting::markSummarySucceeded).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(meeting::markSummaryFailed).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(meeting::markNodesSucceeded).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(meeting::markNodesFailed).isInstanceOf(IllegalStateException.class);
    }

    @DisplayName("SUCCEEDED 또는 FAILED 작업은 다른 최종 상태로 변경할 수 없다.")
    @Test
    void cannotChangeFinalTaskStatus() {
        Meeting meeting = createMeeting();
        meeting.confirmAnalysisOptions(true, true);
        meeting.markSummarySucceeded();
        meeting.markNodesFailed();

        assertThatThrownBy(meeting::markSummarySucceeded).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(meeting::markSummaryFailed).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(meeting::markNodesSucceeded).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(meeting::markNodesFailed).isInstanceOf(IllegalStateException.class);
    }

    @DisplayName("Project가 null이면 Meeting을 생성할 수 없다.")
    @Test
    void projectMustNotBeNull() {
        Project project = createProject();
        assertThatThrownBy(() -> Meeting.create(
                null,
                project.getProjectMembers().get(0),
                "550e8400-e29b-41d4-a716-446655440000"
        ))
                .isInstanceOf(NullPointerException.class)
                .hasMessage("project must not be null");
    }

    @DisplayName("roomName이 null 또는 blank면 Meeting을 생성할 수 없다.")
    @ParameterizedTest
    @org.junit.jupiter.params.provider.NullAndEmptySource
    @org.junit.jupiter.params.provider.ValueSource(strings = {" ", "   "})
    void roomNameMustNotBeBlank(String roomName) {
        Project project = createProject();
        assertThatThrownBy(() -> Meeting.create(
                project, project.getProjectMembers().get(0), roomName
        ))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @DisplayName("roomName이 128자를 초과하면 Meeting을 생성할 수 없다.")
    @Test
    void roomNameMustNotExceed128Characters() {
        Project project = createProject();
        assertThatThrownBy(() -> Meeting.create(
                project, project.getProjectMembers().get(0), "a".repeat(129)
        ))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void creatorMustBelongToMeetingProject() {
        Project project = createProject();
        Project otherProject = createProject();

        assertThatThrownBy(() -> Meeting.create(
                project,
                otherProject.getProjectMembers().get(0),
                "550e8400-e29b-41d4-a716-446655440000"
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void creatorCanBeRegisteredOnceAndCannotBeReplaced() {
        Project project = createProject();
        ProjectMember first = project.getProjectMembers().get(0);
        ProjectMember second = ProjectMember.createMember(2, ProjectRole.MEMBER);
        project.addMember(second);
        Meeting meeting = Meeting.create(
                project, first, "550e8400-e29b-41d4-a716-446655440000"
        );
        org.springframework.test.util.ReflectionTestUtils.setField(
                meeting, "creatorMemberId", null
        );

        assertThat(meeting.registerCreator(first)).isTrue();
        assertThat(meeting.registerCreator(first)).isFalse();
        assertThatThrownBy(() -> meeting.registerCreator(second))
                .isInstanceOf(IllegalStateException.class);
        assertThat(meeting.getCreatorMemberId()).isEqualTo(first.getMemberId());
    }

    private Meeting createMeeting() {
        Project project = createProject();
        return Meeting.create(
                project,
                project.getProjectMembers().get(0),
                "550e8400-e29b-41d4-a716-446655440000"
        );
    }

    private Project createProject() {
        Project project = Project.builder()
                .title("project")
                .content("content")
                .build();
        project.addMember(ProjectMember.createMember(1, ProjectRole.OWNER));
        return project;
    }
}
