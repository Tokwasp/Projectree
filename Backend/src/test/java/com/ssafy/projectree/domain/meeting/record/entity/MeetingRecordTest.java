package com.ssafy.projectree.domain.meeting.record.entity;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MeetingRecordTest {

    private static final UUID COMMAND_ID = UUID.fromString("11111111-1111-1111-1111-111111111111");
    private static final String ROOM_NAME = "550e8400-e29b-41d4-a716-446655440000";

    @DisplayName("회의록을 생성하면 Meeting 참조와 commandId, 제목, 본문 JSON을 저장하고 version은 0이다.")
    @Test
    void createsMeetingRecord() {
        Meeting meeting = createMeeting();

        MeetingRecord record = MeetingRecord.create(
                meeting,
                COMMAND_ID,
                "회의록 제목",
                "[\"요약\"]",
                "[\"결정\"]",
                "[\"할 일\"]",
                "[\"이슈\"]"
        );

        assertThat(record.getMeeting()).isSameAs(meeting);
        assertThat(record.getCommandId()).isEqualTo(COMMAND_ID.toString());
        assertThat(record.getTitle()).isEqualTo("회의록 제목");
        assertThat(record.getSummaryJson()).isEqualTo("[\"요약\"]");
        assertThat(record.getDecisionsJson()).isEqualTo("[\"결정\"]");
        assertThat(record.getNextTodosJson()).isEqualTo("[\"할 일\"]");
        assertThat(record.getIssuesJson()).isEqualTo("[\"이슈\"]");
        assertThat(record.getVersion()).isZero();
    }

    @DisplayName("본문 JSON 컬럼은 null을 허용한다.")
    @Test
    void allowsNullContentJson() {
        MeetingRecord record = MeetingRecord.create(
                createMeeting(), COMMAND_ID, "회의록 제목", null, null, null, null
        );

        assertThat(record.getSummaryJson()).isNull();
        assertThat(record.getDecisionsJson()).isNull();
        assertThat(record.getNextTodosJson()).isNull();
        assertThat(record.getIssuesJson()).isNull();
    }

    @DisplayName("commandId가 null이면 회의록을 생성할 수 없다.")
    @Test
    void rejectsNullCommandId() {
        Meeting meeting = createMeeting();

        assertThatThrownBy(() -> MeetingRecord.create(
                meeting, null, "회의록 제목", null, null, null, null
        )).isInstanceOf(NullPointerException.class);
    }

    @DisplayName("Meeting이 null이면 회의록을 생성할 수 없다.")
    @Test
    void rejectsNullMeeting() {
        assertThatThrownBy(() -> MeetingRecord.create(
                null, COMMAND_ID, "회의록 제목", null, null, null, null
        )).isInstanceOf(NullPointerException.class);
    }

    @DisplayName("제목이 null이거나 비어 있으면 회의록을 생성할 수 없다.")
    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "\t", "\n"})
    void rejectsBlankTitle(String title) {
        Meeting meeting = createMeeting();

        assertThatThrownBy(() -> MeetingRecord.create(
                meeting, COMMAND_ID, title, null, null, null, null
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @DisplayName("제목이 200자를 넘으면 회의록을 생성할 수 없다.")
    @Test
    void rejectsTooLongTitle() {
        Meeting meeting = createMeeting();
        String tooLongTitle = "가".repeat(201);

        assertThatThrownBy(() -> MeetingRecord.create(
                meeting, COMMAND_ID, tooLongTitle, null, null, null, null
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @DisplayName("제목이 정확히 200자면 회의록을 생성할 수 있다.")
    @Test
    void allowsTitleAtMaximumLength() {
        String maximumTitle = "가".repeat(200);

        MeetingRecord record = MeetingRecord.create(
                createMeeting(), COMMAND_ID, maximumTitle, null, null, null, null
        );

        assertThat(record.getTitle()).hasSize(200);
    }

    @DisplayName("수정은 제목과 본문만 변경하고 Meeting과 commandId는 유지한다.")
    @Test
    void updateChangesOnlyEditableFields() {
        Meeting meeting = createMeeting();
        MeetingRecord record = MeetingRecord.create(
                meeting, COMMAND_ID, "원본 제목", "[\"원본 요약\"]", null, null, null
        );

        record.update(
                "수정한 제목",
                "[\"수정한 요약\"]",
                "[\"수정한 결정\"]",
                "[\"수정한 할 일\"]",
                "[\"수정한 이슈\"]"
        );

        assertThat(record.getTitle()).isEqualTo("수정한 제목");
        assertThat(record.getSummaryJson()).isEqualTo("[\"수정한 요약\"]");
        assertThat(record.getDecisionsJson()).isEqualTo("[\"수정한 결정\"]");
        assertThat(record.getNextTodosJson()).isEqualTo("[\"수정한 할 일\"]");
        assertThat(record.getIssuesJson()).isEqualTo("[\"수정한 이슈\"]");
        assertThat(record.getMeeting()).isSameAs(meeting);
        assertThat(record.getCommandId()).isEqualTo(COMMAND_ID.toString());
        assertThat(record.getVersion()).isZero();
    }

    @DisplayName("수정 시에도 제목 제약을 검증하고 실패하면 기존 값을 유지한다.")
    @Test
    void updateValidatesTitle() {
        MeetingRecord record = MeetingRecord.create(
                createMeeting(), COMMAND_ID, "원본 제목", "[\"원본 요약\"]", null, null, null
        );

        assertThatThrownBy(() -> record.update(" ", null, null, null, null))
                .isInstanceOf(IllegalArgumentException.class);
        assertThat(record.getTitle()).isEqualTo("원본 제목");
        assertThat(record.getSummaryJson()).isEqualTo("[\"원본 요약\"]");
    }

    @DisplayName("회의록에는 setter가 존재하지 않는다.")
    @Test
    void hasNoSetters() {
        assertThat(MeetingRecord.class.getMethods())
                .noneMatch(method -> method.getName().startsWith("set"));
    }

    private Meeting createMeeting() {
        Project project = createProject();
        return Meeting.create(project, project.getProjectMembers().get(0), ROOM_NAME);
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
