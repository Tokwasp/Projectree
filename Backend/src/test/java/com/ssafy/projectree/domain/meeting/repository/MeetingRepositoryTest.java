package com.ssafy.projectree.domain.meeting.repository;

import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.config.JpaAuditingConfig;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import java.sql.SQLIntegrityConstraintViolationException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@Import(JpaAuditingConfig.class)
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@DataJpaTest
class MeetingRepositoryTest {

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @DisplayName("Meeting 저장 시 Project FK, 분석 상태와 감사 시각이 저장된다.")
    @Test
    void saveMeeting() {
        Project project = saveProject("project");

        Meeting saved = meetingRepository.saveAndFlush(
                Meeting.create(
                        project,
                        creator(project),
                        "550e8400-e29b-41d4-a716-446655440000"
                )
        );
        entityManager.clear();

        Meeting found = meetingRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getProject().getId()).isEqualTo(project.getId());
        assertThat(found.getCreatorMemberId()).isEqualTo(creator(project).getMemberId());
        assertThat(found.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.NOT_REQUESTED);
        assertThat(found.getNodeStatus()).isEqualTo(AnalysisTaskStatus.NOT_REQUESTED);
        assertThat(found.getCreatedAt()).isNotNull();
        assertThat(found.getUpdatedAt()).isNotNull();
    }

    @DisplayName("roomName으로 Meeting 존재 여부와 엔티티를 조회한다.")
    @Test
    void findByRoomName() {
        Project project = saveProject("project");
        String roomName = "550e8400-e29b-41d4-a716-446655440000";
        meetingRepository.saveAndFlush(Meeting.create(project, creator(project), roomName));

        assertThat(meetingRepository.existsByRoomName(roomName)).isTrue();
        assertThat(meetingRepository.findByRoomName(roomName))
                .isPresent()
                .get()
                .extracting(Meeting::getRoomName)
                .isEqualTo(roomName);
    }

    @DisplayName("roomName UNIQUE 제약이 중복 Meeting 저장을 차단한다.")
    @Test
    void roomNameMustBeUnique() {
        Project project = saveProject("project");
        String roomName = "550e8400-e29b-41d4-a716-446655440000";
        meetingRepository.saveAndFlush(Meeting.create(project, creator(project), roomName));

        assertThatThrownBy(() ->
                meetingRepository.saveAndFlush(
                        Meeting.create(project, creator(project), roomName)
                ))
                .rootCause()
                .isInstanceOf(SQLIntegrityConstraintViolationException.class);
    }

    @DisplayName("존재하지 않는 Project ID로 Meeting을 저장할 수 없다.")
    @Test
    void projectForeignKeyIsEnforced() {
        assertThatThrownBy(() -> entityManager.createNativeQuery("""
                insert into meeting (
                    project_id, room_name,
                    generate_summary, summary_status,
                    generate_nodes, node_status,
                    created_at, updated_at
                ) values (
                    999999, 'orphan-room',
                    false, 'NOT_REQUESTED',
                    false, 'NOT_REQUESTED',
                    current_timestamp, current_timestamp
                )
                """).executeUpdate())
                .rootCause()
                .isInstanceOf(SQLIntegrityConstraintViolationException.class);
    }

    @DisplayName("상태 Enum은 ordinal이 아닌 문자열로 저장된다.")
    @Test
    void taskStatusesAreStoredAsStrings() {
        Project project = saveProject("project");
        Meeting meeting = Meeting.create(
                project,
                creator(project),
                "550e8400-e29b-41d4-a716-446655440000"
        );
        meeting.confirmAnalysisOptions(true, false);
        meetingRepository.saveAndFlush(meeting);

        Object[] row = (Object[]) entityManager.createNativeQuery(
                "select summary_status, node_status from meeting"
        ).getSingleResult();
        assertThat(row).containsExactly("PROCESSING", "SKIPPED");
    }

    private Project saveProject(String title) {
        Project project = Project.builder()
                .title(title)
                .content("content")
                .build();
        project.addMember(ProjectMember.createMember(1, ProjectRole.OWNER));
        return projectRepository.saveAndFlush(project);
    }

    private ProjectMember creator(Project project) {
        return project.getProjectMembers().get(0);
    }
}
