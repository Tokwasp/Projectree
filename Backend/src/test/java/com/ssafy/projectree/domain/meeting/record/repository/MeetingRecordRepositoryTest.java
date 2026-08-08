package com.ssafy.projectree.domain.meeting.record.repository;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.config.JpaAuditingConfig;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.hibernate.Hibernate;
import org.hibernate.SessionFactory;
import org.hibernate.stat.Statistics;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
import org.springframework.boot.jdbc.test.autoconfigure.AutoConfigureTestDatabase;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.ActiveProfiles;

import java.sql.SQLIntegrityConstraintViolationException;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.tuple;

@ActiveProfiles("test")
@Import(JpaAuditingConfig.class)
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@DataJpaTest
class MeetingRecordRepositoryTest {

    private static final String ROOM_NAME = "550e8400-e29b-41d4-a716-446655440000";
    private static final String OTHER_ROOM_NAME = "550e8400-e29b-41d4-a716-446655440001";
    private static final String EXCLUDED_ROOM_NAME = "550e8400-e29b-41d4-a716-446655440002";

    @Autowired
    private MeetingRecordRepository meetingRecordRepository;

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @PersistenceContext
    private EntityManager entityManager;

    @DisplayName("회의록 저장 시 Meeting FK, commandId, 제목, TEXT 본문, 감사 시각이 저장되고 version은 0이다.")
    @Test
    void saveMeetingRecord() {
        Meeting meeting = saveMeeting(ROOM_NAME);
        UUID commandId = UUID.randomUUID();
        String summaryJson = "[\"첫 번째 요약\",\"그가 \\\"확정\\\"이라고 말했다\"]";

        MeetingRecord saved = meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting,
                commandId,
                "회의록 제목",
                summaryJson,
                "[\"결정\"]",
                "[\"할 일\"]",
                "[\"이슈\"]"
        ));
        entityManager.clear();

        MeetingRecord found = meetingRecordRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getMeeting().getId()).isEqualTo(meeting.getId());
        assertThat(found.getCommandId()).isEqualTo(commandId.toString());
        assertThat(found.getTitle()).isEqualTo("회의록 제목");
        assertThat(found.getSummaryJson()).isEqualTo(summaryJson);
        assertThat(found.getDecisionsJson()).isEqualTo("[\"결정\"]");
        assertThat(found.getNextTodosJson()).isEqualTo("[\"할 일\"]");
        assertThat(found.getIssuesJson()).isEqualTo("[\"이슈\"]");
        assertThat(found.getCreatedAt()).isNotNull();
        assertThat(found.getUpdatedAt()).isNotNull();
        assertThat(found.getVersion()).isZero();
    }

    @DisplayName("본문 TEXT 컬럼은 NULL로 저장할 수 있다.")
    @Test
    void saveMeetingRecordWithNullContent() {
        Meeting meeting = saveMeeting(ROOM_NAME);

        MeetingRecord saved = meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting, UUID.randomUUID(), "회의록 제목", null, null, null, null
        ));
        entityManager.clear();

        MeetingRecord found = meetingRecordRepository.findById(saved.getId()).orElseThrow();
        assertThat(found.getSummaryJson()).isNull();
        assertThat(found.getDecisionsJson()).isNull();
        assertThat(found.getNextTodosJson()).isNull();
        assertThat(found.getIssuesJson()).isNull();
    }

    @DisplayName("meetingId로 회의록 존재 여부와 엔티티를 조회한다.")
    @Test
    void findByMeetingId() {
        Meeting meeting = saveMeeting(ROOM_NAME);
        meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting, UUID.randomUUID(), "회의록 제목", null, null, null, null
        ));
        entityManager.clear();

        assertThat(meetingRecordRepository.existsByMeetingId(meeting.getId())).isTrue();
        assertThat(meetingRecordRepository.findByMeetingId(meeting.getId()))
                .isPresent()
                .get()
                .extracting(MeetingRecord::getTitle)
                .isEqualTo("회의록 제목");
        assertThat(meetingRecordRepository.findByMeetingId(meeting.getId() + 1000)).isEmpty();
        assertThat(meetingRecordRepository.existsByMeetingId(meeting.getId() + 1000)).isFalse();
    }

    @DisplayName("meetingId 목록으로 여러 회의록을 조회하면 목록에 포함된 Meeting의 회의록만 반환된다.")
    @Test
    void findByMeetingIdIn() {
        // given
        Project project = saveProject();
        Meeting first = saveMeeting(project, ROOM_NAME);
        Meeting second = saveMeeting(project, OTHER_ROOM_NAME);
        Meeting excluded = saveMeeting(project, EXCLUDED_ROOM_NAME);
        saveMeetingRecord(first, "첫 번째 회의록");
        saveMeetingRecord(second, "두 번째 회의록");
        saveMeetingRecord(excluded, "조회 대상이 아닌 회의록");
        entityManager.clear();

        // when
        List<MeetingRecord> found =
                meetingRecordRepository.findByMeetingIdIn(List.of(first.getId(), second.getId()));

        // then
        assertThat(found).hasSize(2)
                .extracting(MeetingRecord::getTitle)
                .containsExactlyInAnyOrder("첫 번째 회의록", "두 번째 회의록");
    }

    @DisplayName("meetingId 목록으로 회의록을 조회하면 Meeting을 fetch join 해 쿼리 한 번으로 회의 정보까지 읽는다.")
    @Test
    void findByMeetingIdInFetchesMeeting() {
        // given
        Project project = saveProject();
        Meeting first = saveMeeting(project, ROOM_NAME);
        Meeting second = saveMeeting(project, OTHER_ROOM_NAME);
        saveMeetingRecord(first, "첫 번째 회의록");
        saveMeetingRecord(second, "두 번째 회의록");
        entityManager.clear();

        Statistics statistics = entityManager.getEntityManagerFactory()
                .unwrap(SessionFactory.class)
                .getStatistics();
        statistics.setStatisticsEnabled(true);
        statistics.clear();

        // when
        List<MeetingRecord> found =
                meetingRecordRepository.findByMeetingIdIn(List.of(first.getId(), second.getId()));

        // then
        assertThat(found).hasSize(2)
                .allSatisfy(record -> assertThat(Hibernate.isInitialized(record.getMeeting())).isTrue())
                .extracting(
                        MeetingRecord::getTitle,
                        record -> record.getMeeting().getId(),
                        record -> record.getMeeting().getRoomName()
                )
                .containsExactlyInAnyOrder(
                        tuple("첫 번째 회의록", first.getId(), ROOM_NAME),
                        tuple("두 번째 회의록", second.getId(), OTHER_ROOM_NAME)
                );
        assertThat(statistics.getPrepareStatementCount()).isEqualTo(1);
    }

    @DisplayName("commandId로 회의록 존재 여부와 엔티티를 조회한다.")
    @Test
    void findByCommandId() {
        Meeting meeting = saveMeeting(ROOM_NAME);
        UUID commandId = UUID.randomUUID();
        meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting, commandId, "회의록 제목", null, null, null, null
        ));
        entityManager.clear();

        assertThat(meetingRecordRepository.existsByCommandId(commandId.toString())).isTrue();
        assertThat(meetingRecordRepository.findByCommandId(commandId.toString()))
                .isPresent()
                .get()
                .extracting(MeetingRecord::getTitle)
                .isEqualTo("회의록 제목");
        assertThat(meetingRecordRepository.findByCommandId(UUID.randomUUID().toString())).isEmpty();
        assertThat(meetingRecordRepository.existsByCommandId(UUID.randomUUID().toString())).isFalse();
    }

    @DisplayName("meeting_id UNIQUE 제약이 한 Meeting에 대한 두 번째 회의록 저장을 차단한다.")
    @Test
    void meetingIdMustBeUnique() {
        Meeting meeting = saveMeeting(ROOM_NAME);
        meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting, UUID.randomUUID(), "첫 번째 회의록", null, null, null, null
        ));

        assertThatThrownBy(() -> meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting, UUID.randomUUID(), "두 번째 회의록", null, null, null, null
        )))
                .rootCause()
                .isInstanceOf(SQLIntegrityConstraintViolationException.class);
    }

    @DisplayName("command_id UNIQUE 제약은 서로 다른 Meeting 사이에서도 중복을 차단한다.")
    @Test
    void commandIdMustBeUniqueAcrossMeetings() {
        Project project = saveProject();
        Meeting meeting = saveMeeting(project, ROOM_NAME);
        Meeting otherMeeting = saveMeeting(project, OTHER_ROOM_NAME);
        UUID commandId = UUID.randomUUID();
        meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting, commandId, "첫 번째 회의록", null, null, null, null
        ));

        assertThatThrownBy(() -> meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                otherMeeting, commandId, "두 번째 회의록", null, null, null, null
        )))
                .rootCause()
                .isInstanceOf(SQLIntegrityConstraintViolationException.class);
    }

    @DisplayName("존재하지 않는 meeting_id로 회의록을 저장할 수 없다.")
    @Test
    void meetingForeignKeyIsEnforced() {
        assertThatThrownBy(() -> entityManager.createNativeQuery("""
                insert into meeting_record (
                    meeting_id, command_id, title,
                    summary, decisions, next_todos, issues,
                    created_at, updated_at, version
                ) values (
                    999999, '11111111-1111-1111-1111-111111111111', 'orphan-record',
                    null, null, null, null,
                    current_timestamp, current_timestamp, 0
                )
                """).executeUpdate())
                .rootCause()
                .isInstanceOf(SQLIntegrityConstraintViolationException.class);
    }

    @DisplayName("순차 수정 시 @Version이 증가한다.")
    @Test
    void versionIncrementsOnUpdate() {
        Meeting meeting = saveMeeting(ROOM_NAME);
        MeetingRecord saved = meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting, UUID.randomUUID(), "원본 제목", "[\"원본 요약\"]", null, null, null
        ));
        assertThat(saved.getVersion()).isZero();
        entityManager.clear();

        MeetingRecord found = meetingRecordRepository.findById(saved.getId()).orElseThrow();
        found.update("수정한 제목", "[\"수정한 요약\"]", null, null, null);
        entityManager.flush();

        assertThat(found.getVersion()).isEqualTo(1L);
        entityManager.clear();
        MeetingRecord reloaded = meetingRecordRepository.findById(saved.getId()).orElseThrow();
        assertThat(reloaded.getVersion()).isEqualTo(1L);
        assertThat(reloaded.getTitle()).isEqualTo("수정한 제목");
        assertThat(reloaded.getSummaryJson()).isEqualTo("[\"수정한 요약\"]");
    }

    private void saveMeetingRecord(Meeting meeting, String title) {
        meetingRecordRepository.saveAndFlush(MeetingRecord.create(
                meeting, UUID.randomUUID(), title, null, null, null, null
        ));
    }

    private Meeting saveMeeting(String roomName) {
        return saveMeeting(saveProject(), roomName);
    }

    private Meeting saveMeeting(Project project, String roomName) {
        return meetingRepository.saveAndFlush(
                Meeting.create(project, project.getProjectMembers().get(0), roomName)
        );
    }

    private Project saveProject() {
        Project project = Project.builder()
                .title("project")
                .content("content")
                .build();
        project.addMember(ProjectMember.createMember(1, ProjectRole.OWNER));
        return projectRepository.saveAndFlush(project);
    }
}
