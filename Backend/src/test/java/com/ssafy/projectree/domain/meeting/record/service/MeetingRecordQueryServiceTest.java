package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.record.codec.MeetingRecordContentCodec;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordDetailResponse;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordContentCodecException;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ErrorCode;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.assertj.core.api.ThrowableAssert.ThrowingCallable;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Duration;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@SpringBootTest
class MeetingRecordQueryServiceTest {

    private static final String ROOM_NAME = "c6db7ac7-d3c7-4f18-928c-ce376ccfabba";
    private static final String OTHER_ROOM_NAME = "550e8400-e29b-41d4-a716-446655440000";
    private static final String TITLE = "AI 노드 구조 및 CI/CD 파이프라인 구축 방안 논의";
    private static final int OUTSIDER_ID = 9_999;

    @MockitoBean
    private GoogleOAuthClient googleOAuthClient;

    @MockitoBean
    private NaverOAuthClient naverOAuthClient;

    @Autowired
    private MeetingRecordQueryService service;

    @Autowired
    private MeetingRecordRepository meetingRecordRepository;

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private MeetingAnalysisCommandOutboxRepository outboxRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private MemberRepository memberRepository;

    @Autowired
    private MeetingRecordContentCodec contentCodec;

    @Autowired
    private PlatformTransactionManager transactionManager;

    @PersistenceContext
    private EntityManager entityManager;

    @AfterEach
    void cleanUp() {
        meetingRecordRepository.deleteAll();
        outboxRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @DisplayName("프로젝트 멤버는 회의록 상세를 조회할 수 있다.")
    @Test
    void getRecord() {
        Fixture fixture = fixture();

        MeetingRecordDetailResponse response = service.getRecord(
                fixture.projectId(), fixture.meetingId(), fixture.memberId()
        );

        MeetingRecord persisted = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(response.meetingRecordId()).isEqualTo(persisted.getId());
        assertThat(response.projectId()).isEqualTo(fixture.projectId());
        assertThat(response.meetingId()).isEqualTo(fixture.meetingId());
        assertThat(response.title()).isEqualTo(TITLE);
        assertThat(response.summary()).containsExactly("첫 번째 요약", "두 번째 요약");
        assertThat(response.decisions()).containsExactly("첫 번째 결정");
        assertThat(response.nextTodos()).containsExactly("첫 번째 할 일");
        assertThat(response.issues()).containsExactly("첫 번째 이슈");
        assertThat(response.version()).isZero();
        assertThat(response.createdAt()).isEqualTo(persisted.getCreatedAt());
        assertThat(response.updatedAt()).isEqualTo(persisted.getUpdatedAt());
    }

    @DisplayName("존재하지 않는 프로젝트는 404다.")
    @Test
    void rejectsUnknownProject() {
        Fixture fixture = fixture();

        assertBusinessError(
                () -> service.getRecord(
                        fixture.projectId() + 1000, fixture.meetingId(), fixture.memberId()
                ),
                ProjectErrorCode.PROJECT_NOT_FOUND
        );
    }

    @DisplayName("프로젝트 멤버가 아니면 회의록 존재 여부를 알려주지 않고 거부한다.")
    @Test
    void rejectsNonProjectMember() {
        Fixture fixture = fixture();

        assertBusinessError(
                () -> service.getRecord(fixture.projectId(), fixture.meetingId(), OUTSIDER_ID),
                ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND
        );
    }

    /**
     * 회의록이 없는 회의에 비회원이 접근해도 MEETING_RECORD_NOT_FOUND가 아니라 권한 오류가 나야 한다.
     * meetingId를 바꿔가며 회의록 존재 여부를 탐색할 수 없어야 하기 때문이다.
     */
    @DisplayName("비회원에게는 회의나 회의록 부재보다 권한 오류가 먼저 적용된다.")
    @Test
    void checksMembershipBeforeMeetingAndRecordExistence() {
        Fixture fixture = fixtureWithoutRecord();

        assertBusinessError(
                () -> service.getRecord(fixture.projectId(), fixture.meetingId(), OUTSIDER_ID),
                ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND
        );
        assertBusinessError(
                () -> service.getRecord(
                        fixture.projectId(), fixture.meetingId() + 1000, OUTSIDER_ID
                ),
                ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND
        );
    }

    @DisplayName("존재하지 않는 회의는 404다.")
    @Test
    void rejectsUnknownMeeting() {
        Fixture fixture = fixture();

        assertBusinessError(
                () -> service.getRecord(
                        fixture.projectId(), fixture.meetingId() + 1000, fixture.memberId()
                ),
                MeetingErrorCode.MEETING_NOT_FOUND
        );
    }

    @DisplayName("회의가 요청한 프로젝트에 속하지 않으면 400이다.")
    @Test
    void rejectsMeetingFromAnotherProject() {
        Fixture fixture = fixture();
        Fixture other = fixtureWithoutRecord(OTHER_ROOM_NAME);
        addMember(other.projectId(), fixture.memberId());

        assertBusinessError(
                () -> service.getRecord(
                        other.projectId(), fixture.meetingId(), fixture.memberId()
                ),
                MeetingErrorCode.MEETING_PROJECT_MISMATCH
        );
    }

    @DisplayName("회의록이 아직 생성되지 않았으면 404다.")
    @Test
    void rejectsMissingRecord() {
        Fixture fixture = fixtureWithoutRecord();

        assertBusinessError(
                () -> service.getRecord(
                        fixture.projectId(), fixture.meetingId(), fixture.memberId()
                ),
                MeetingRecordErrorCode.MEETING_RECORD_NOT_FOUND
        );
    }

    @DisplayName("시작은 Meeting 생성 시각, 종료는 분석 요청 확정 시각으로 추정한다.")
    @Test
    void estimatesTimeFromMeetingAndOutbox() {
        Fixture fixture = fixture();

        MeetingRecordDetailResponse response = service.getRecord(
                fixture.projectId(), fixture.meetingId(), fixture.memberId()
        );

        Meeting persistedMeeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        MeetingAnalysisCommandOutbox persistedOutbox = outboxRepository
                .findByCommandIdWithMeetingAndProject(fixture.commandId().toString())
                .orElseThrow();
        assertThat(response.startedAt()).isEqualTo(persistedMeeting.getCreatedAt());
        assertThat(response.endedAt()).isEqualTo(persistedOutbox.getCreatedAt());
        assertThat(response.meetingDate()).isEqualTo(persistedMeeting.getCreatedAt().toLocalDate());
        assertThat(response.durationMinutes()).isEqualTo(Duration.between(
                persistedMeeting.getCreatedAt(), persistedOutbox.getCreatedAt()
        ).toMinutes());
        assertThat(response.durationMinutes()).isNotNegative();
    }

    @DisplayName("Outbox가 없으면 회의록 생성 시각을 종료 추정값으로 사용한다.")
    @Test
    void fallsBackToRecordCreatedAtWhenOutboxIsMissing() {
        Fixture fixture = fixture();
        executeInTransaction(() -> entityManager
                .createNativeQuery("delete from meeting_analysis_command_outbox where meeting_id = :meetingId")
                .setParameter("meetingId", fixture.meetingId())
                .executeUpdate());
        // Outbox가 실제로 사라졌음을 확인해, 우연히 같은 시각이라 통과하는 상황을 배제한다.
        assertThat(outboxRepository.findByCommandIdWithMeetingAndProject(
                fixture.commandId().toString()
        )).isEmpty();

        MeetingRecordDetailResponse response = service.getRecord(
                fixture.projectId(), fixture.meetingId(), fixture.memberId()
        );

        Meeting persistedMeeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        MeetingRecord persistedRecord = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(response.startedAt()).isEqualTo(persistedMeeting.getCreatedAt());
        assertThat(response.endedAt()).isEqualTo(persistedRecord.getCreatedAt());
        assertThat(response.durationMinutes()).isNotNegative();
    }

    @DisplayName("본문 컬럼이 NULL이면 네 영역 모두 빈 목록으로 응답한다.")
    @Test
    void returnsEmptyListsForNullContent() {
        Fixture fixture = fixtureWithoutRecord();
        saveRecord(fixture, null, null, null, null);

        MeetingRecordDetailResponse response = service.getRecord(
                fixture.projectId(), fixture.meetingId(), fixture.memberId()
        );

        assertThat(response.summary()).isEmpty();
        assertThat(response.decisions()).isEmpty();
        assertThat(response.nextTodos()).isEmpty();
        assertThat(response.issues()).isEmpty();
    }

    @DisplayName("빈 JSON 배열도 빈 목록으로 응답한다.")
    @Test
    void returnsEmptyListsForEmptyJsonArray() {
        Fixture fixture = fixtureWithoutRecord();
        saveRecord(fixture, "[]", "[]", "[]", "[]");

        MeetingRecordDetailResponse response = service.getRecord(
                fixture.projectId(), fixture.meetingId(), fixture.memberId()
        );

        assertThat(response.summary()).isEmpty();
        assertThat(response.decisions()).isEmpty();
        assertThat(response.nextTodos()).isEmpty();
        assertThat(response.issues()).isEmpty();
    }

    @DisplayName("저장된 배열 순서를 그대로 유지해 응답한다.")
    @Test
    void preservesStoredOrder() {
        Fixture fixture = fixtureWithoutRecord();
        List<String> stored = List.of("두 번째", "첫 번째", "세 번째");
        saveRecord(fixture, contentCodec.encode(stored), "[]", "[]", "[]");

        MeetingRecordDetailResponse response = service.getRecord(
                fixture.projectId(), fixture.meetingId(), fixture.memberId()
        );

        assertThat(response.summary()).containsExactlyElementsOf(stored);
    }

    @DisplayName("조회는 회의 상태와 회의록 version, 감사 시각을 바꾸지 않는다.")
    @Test
    void doesNotMutateAnyState() {
        Fixture fixture = fixture();
        Meeting before = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        MeetingRecord recordBefore = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        AnalysisTaskStatus summaryStatusBefore = before.getSummaryStatus();
        AnalysisTaskStatus nodeStatusBefore = before.getNodeStatus();
        long versionBefore = recordBefore.getVersion();
        LocalDateTime updatedAtBefore = recordBefore.getUpdatedAt();

        service.getRecord(fixture.projectId(), fixture.meetingId(), fixture.memberId());
        clearPersistenceContext();

        Meeting after = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        MeetingRecord recordAfter = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(after.getSummaryStatus()).isEqualTo(summaryStatusBefore);
        assertThat(after.getNodeStatus()).isEqualTo(nodeStatusBefore);
        assertThat(recordAfter.getVersion()).isEqualTo(versionBefore);
        assertThat(recordAfter.getUpdatedAt()).isEqualTo(updatedAtBefore);
    }

    /**
     * 깨진 JSON을 빈 목록으로 조용히 감추면 데이터 손상이 드러나지 않는다.
     */
    @DisplayName("저장된 JSON이 깨져 있으면 빈 목록으로 감추지 않고 예외를 그대로 노출한다.")
    @Test
    void doesNotHideCorruptedJson() {
        Fixture fixture = fixtureWithoutRecord();
        saveRecord(fixture, "{\"not\":\"array\"}", "[]", "[]", "[]");

        assertThatThrownBy(() -> service.getRecord(
                fixture.projectId(), fixture.meetingId(), fixture.memberId()
        )).isInstanceOf(MeetingRecordContentCodecException.class);

        MeetingRecord unchanged = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(unchanged.getSummaryJson()).isEqualTo("{\"not\":\"array\"}");
        assertThat(unchanged.getVersion()).isZero();
    }

    private Fixture fixture() {
        Fixture fixture = fixtureWithoutRecord();
        saveRecord(
                fixture,
                contentCodec.encode(List.of("첫 번째 요약", "두 번째 요약")),
                contentCodec.encode(List.of("첫 번째 결정")),
                contentCodec.encode(List.of("첫 번째 할 일")),
                contentCodec.encode(List.of("첫 번째 이슈"))
        );
        return fixture;
    }

    private Fixture fixtureWithoutRecord() {
        return fixtureWithoutRecord(ROOM_NAME);
    }

    private Fixture fixtureWithoutRecord(String roomName) {
        String suffix = UUID.randomUUID().toString();
        Member member = memberRepository.saveAndFlush(
                Member.builder()
                        .email("member-" + suffix + "@example.com")
                        .name("member")
                        .build()
        );
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(member.getId(), ProjectRole.OWNER);
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);

        Meeting meeting = Meeting.create(project, creator, roomName);
        meeting.confirmAnalysisOptions(true, false);
        meeting = meetingRepository.saveAndFlush(meeting);

        UUID commandId = UUID.randomUUID();
        int meetingId = meeting.getId();
        int memberId = member.getId();
        executeInTransaction(() -> {
            entityManager.persist(MeetingAnalysisCommandOutbox.pending(
                    commandId,
                    entityManager.find(Meeting.class, meetingId),
                    MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                    "{}",
                    memberId,
                    LocalDateTime.now()
            ));
            return null;
        });

        return new Fixture(project.getId(), meetingId, memberId, commandId);
    }

    private void saveRecord(
            Fixture fixture,
            String summaryJson,
            String decisionsJson,
            String nextTodosJson,
            String issuesJson
    ) {
        executeInTransaction(() -> {
            entityManager.persist(MeetingRecord.create(
                    entityManager.find(Meeting.class, fixture.meetingId()),
                    fixture.commandId(),
                    TITLE,
                    summaryJson,
                    decisionsJson,
                    nextTodosJson,
                    issuesJson
            ));
            return null;
        });
    }

    private void addMember(int projectId, int memberId) {
        executeInTransaction(() -> {
            entityManager.find(Project.class, projectId)
                    .addMember(ProjectMember.createMember(memberId, ProjectRole.MEMBER));
            return null;
        });
    }

    private void clearPersistenceContext() {
        executeInTransaction(() -> {
            entityManager.clear();
            return null;
        });
    }

    private <T> T executeInTransaction(TransactionCallback<T> callback) {
        return new TransactionTemplate(transactionManager).execute(status -> {
            T result = callback.execute();
            entityManager.flush();
            return result;
        });
    }

    private interface TransactionCallback<T> {
        T execute();
    }

    private void assertBusinessError(ThrowingCallable callable, ErrorCode errorCode) {
        assertThatThrownBy(callable)
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(errorCode);
    }

    private record Fixture(int projectId, int meetingId, int memberId, UUID commandId) {
    }
}
