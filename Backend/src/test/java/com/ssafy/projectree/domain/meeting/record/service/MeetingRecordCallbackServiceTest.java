package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.record.codec.MeetingRecordContentCodec;
import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordCallbackRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordCallbackResponse;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.record.event.MeetingRecordCreatedNotificationEvent;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordContentCodecException;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.notification.repository.NotificationRepository;
import com.ssafy.projectree.domain.notification.service.NotificationPublisher;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ErrorCode;
import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.assertj.core.api.ThrowableAssert.ThrowingCallable;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.context.event.ApplicationEvents;
import org.springframework.test.context.event.RecordApplicationEvents;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.reset;

@ActiveProfiles("test")
@SpringBootTest
@RecordApplicationEvents
class MeetingRecordCallbackServiceTest {

    private static final String ROOM_NAME = "c6db7ac7-d3c7-4f18-928c-ce376ccfabba";
    private static final String OTHER_ROOM_NAME = "550e8400-e29b-41d4-a716-446655440000";
    private static final String TITLE = "AI 노드 구조 및 CI/CD 파이프라인 구축 방안 논의";

    @MockitoBean
    private GoogleOAuthClient googleOAuthClient;

    @MockitoBean
    private NaverOAuthClient naverOAuthClient;

    @MockitoBean
    private NotificationPublisher notificationPublisher;

    @Autowired
    private ApplicationEvents applicationEvents;

    @Autowired
    private MeetingRecordCallbackService service;

    @Autowired
    private MeetingRecordRepository meetingRecordRepository;

    @Autowired
    private NotificationRepository notificationRepository;

    @MockitoSpyBean
    private MeetingRecordRepository meetingRecordRepositorySpy;

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
        notificationRepository.deleteAll();
        meetingRecordRepository.deleteAll();
        outboxRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @DisplayName("최초 Callback은 회의록을 생성하고 요약 상태를 완료로 바꾼다.")
    @Test
    void createsMeetingRecordOnFirstCallback() {
        Fixture fixture = fixture(true);

        MeetingRecordCallbackResponse response = service.receive(
                fixture.meetingId(), request(fixture.commandId())
        );

        assertThat(response.duplicated()).isFalse();
        assertThat(response.meetingId()).isEqualTo(fixture.meetingId());
        assertThat(response.commandId()).isEqualTo(fixture.commandId());
        assertThat(response.version()).isZero();
        assertThat(response.meetingRecordId()).isPositive();

        MeetingRecord saved = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(saved.getCommandId()).isEqualTo(fixture.commandId().toString());
        assertThat(saved.getTitle()).isEqualTo(TITLE);
        assertThat(saved.getVersion()).isZero();
        assertThat(saved.getCreatedAt()).isNotNull();
        assertThat(saved.getUpdatedAt()).isNotNull();
        assertThat(contentCodec.decode(saved.getSummaryJson()))
                .containsExactly("첫 번째 전체 요약", "두 번째 전체 요약");
        assertThat(contentCodec.decode(saved.getDecisionsJson()))
                .containsExactly("첫 번째 결정 사항");
        assertThat(contentCodec.decode(saved.getNextTodosJson()))
                .containsExactly("첫 번째 다음 할 일");
        assertThat(contentCodec.decode(saved.getIssuesJson()))
                .containsExactly("첫 번째 이슈");
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.SUCCEEDED);

        assertThat(publishedEvents())
                .singleElement()
                .extracting(MeetingRecordCreatedNotificationEvent::receiverId)
                .isEqualTo(fixture.memberId());
    }

    @DisplayName("빈 배열은 TEXT 컬럼에 빈 JSON 배열로 저장된다.")
    @Test
    void storesEmptyArraysAsEmptyJsonArray() {
        Fixture fixture = fixture(true);

        service.receive(fixture.meetingId(), new MeetingRecordCallbackRequest(
                1, fixture.commandId(), TITLE, List.of(), List.of(), List.of(), List.of()
        ));

        Object[] row = (Object[]) queryInTransaction(
                "select summary, decisions, next_todos, issues from meeting_record"
        );
        assertThat(row).containsExactly("[]", "[]", "[]", "[]");
    }

    @DisplayName("동일 Callback 재시도는 기존 회의록을 그대로 반환하고 아무것도 바꾸지 않는다.")
    @Test
    void retryReturnsExistingRecordWithoutChange() {
        Fixture fixture = fixture(true);
        MeetingRecordCallbackResponse first = service.receive(
                fixture.meetingId(), request(fixture.commandId())
        );

        MeetingRecordCallbackResponse retry = service.receive(
                fixture.meetingId(), request(fixture.commandId())
        );

        assertThat(retry.duplicated()).isTrue();
        assertThat(retry.meetingRecordId()).isEqualTo(first.meetingRecordId());
        assertThat(retry.version()).isZero();
        assertThat(meetingRecordRepository.count()).isEqualTo(1);

        MeetingRecord stored = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(stored.getTitle()).isEqualTo(TITLE);
        assertThat(stored.getVersion()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.SUCCEEDED);
        assertThat(publishedEvents()).hasSize(1);
    }

    @DisplayName("사용자가 수정한 회의록은 동일 Callback 재시도로 덮어써지지 않는다.")
    @Test
    void retryDoesNotOverwriteUserEdits() {
        Fixture fixture = fixture(true);
        service.receive(fixture.meetingId(), request(fixture.commandId()));
        long editedVersion = editRecordAsUser(fixture.meetingId());

        MeetingRecordCallbackResponse retry = service.receive(
                fixture.meetingId(),
                new MeetingRecordCallbackRequest(
                        1,
                        fixture.commandId(),
                        "Python이 다시 보낸 제목",
                        List.of("Python이 다시 보낸 요약"),
                        List.of("Python이 다시 보낸 결정"),
                        List.of("Python이 다시 보낸 할 일"),
                        List.of("Python이 다시 보낸 이슈")
                )
        );

        assertThat(retry.duplicated()).isTrue();
        assertThat(retry.version()).isEqualTo(editedVersion);

        MeetingRecord stored = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(stored.getTitle()).isEqualTo("사용자가 고친 제목");
        assertThat(contentCodec.decode(stored.getSummaryJson()))
                .containsExactly("사용자가 고친 요약");
        assertThat(stored.getVersion()).isEqualTo(editedVersion);
        assertThat(meetingRecordRepository.count()).isEqualTo(1);
        assertThat(publishedEvents()).hasSize(1);
    }

    /**
     * meeting_analysis_command_outbox는 (meeting_id, command_type) UNIQUE라서 한 회의에
     * 분석 요청 Command가 둘 이상 존재할 수 없다. 따라서 이 충돌은 회의록이 이미 생성된 뒤
     * 해당 회의의 Command가 새 commandId로 다시 발행된 경우에만 도달한다.
     */
    @DisplayName("회의록 생성 후 Command가 다시 발행되면 다른 commandId Callback은 충돌이고 기존 내용은 유지된다.")
    @Test
    void rejectsAnotherCommandForSameMeeting() {
        Fixture fixture = fixture(true);
        service.receive(fixture.meetingId(), request(fixture.commandId()));
        UUID otherCommandId = reissueCommand(fixture.meetingId());

        assertBusinessError(
                () -> service.receive(fixture.meetingId(), new MeetingRecordCallbackRequest(
                        1,
                        otherCommandId,
                        "다른 Command 제목",
                        List.of("다른 Command 요약"),
                        List.of(),
                        List.of(),
                        List.of()
                )),
                MeetingRecordErrorCode.MEETING_RECORD_ALREADY_CREATED_BY_ANOTHER_COMMAND
        );

        MeetingRecord stored = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(stored.getTitle()).isEqualTo(TITLE);
        assertThat(stored.getCommandId()).isEqualTo(fixture.commandId().toString());
        assertThat(stored.getVersion()).isZero();
        assertThat(meetingRecordRepository.count()).isEqualTo(1);
    }

    @DisplayName("Command가 가리키는 회의와 URL meetingId가 다르면 충돌이고 회의록은 생성되지 않는다.")
    @Test
    void rejectsCommandBelongingToAnotherMeeting() {
        Fixture fixture = fixture(true);
        Fixture other = fixture(true, OTHER_ROOM_NAME);

        assertBusinessError(
                () -> service.receive(other.meetingId(), request(fixture.commandId())),
                MeetingRecordErrorCode.MEETING_RECORD_COMMAND_MISMATCH
        );

        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(other.meetingId())).isEqualTo(AnalysisTaskStatus.PROCESSING);
    }

    @DisplayName("존재하지 않는 commandId는 404다.")
    @Test
    void rejectsUnknownCommandId() {
        Fixture fixture = fixture(true);

        assertBusinessError(
                () -> service.receive(fixture.meetingId(), request(UUID.randomUUID())),
                MeetingRecordErrorCode.MEETING_RECORD_COMMAND_NOT_FOUND
        );

        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.PROCESSING);
    }

    @DisplayName("존재하지 않는 meetingId는 회의 조회 단계에서 실패한다.")
    @Test
    void rejectsUnknownMeetingId() {
        Fixture fixture = fixture(true);

        assertBusinessError(
                () -> service.receive(fixture.meetingId() + 1000, request(fixture.commandId())),
                MeetingErrorCode.MEETING_NOT_FOUND
        );

        assertThat(meetingRecordRepository.count()).isZero();
    }

    @DisplayName("요약 생성을 요청하지 않은 회의는 회의록을 만들 수 없다.")
    @Test
    void rejectsMeetingThatDidNotRequestSummary() {
        Fixture fixture = fixture(false);

        assertBusinessError(
                () -> service.receive(fixture.meetingId(), request(fixture.commandId())),
                MeetingRecordErrorCode.MEETING_RECORD_SUMMARY_NOT_REQUESTED
        );

        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.SKIPPED);
    }

    @DisplayName("지원하지 않는 Callback 스키마 버전은 400이다.")
    @ParameterizedTest
    @ValueSource(ints = {0, 2, -1, 99})
    void rejectsUnsupportedSchemaVersion(int callbackSchemaVersion) {
        Fixture fixture = fixture(true);

        assertBusinessError(
                () -> service.receive(fixture.meetingId(), new MeetingRecordCallbackRequest(
                        callbackSchemaVersion,
                        fixture.commandId(),
                        TITLE,
                        List.of("요약"),
                        List.of(),
                        List.of(),
                        List.of()
                )),
                MeetingRecordErrorCode.MEETING_RECORD_CALLBACK_SCHEMA_UNSUPPORTED
        );

        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.PROCESSING);
    }

    @DisplayName("본문 직렬화가 실패하면 회의록과 요약 상태 변경이 함께 롤백된다.")
    @Test
    void rollsBackWhenContentSerializationFails() {
        Fixture fixture = fixture(true);

        assertThatThrownBy(() -> service.receive(fixture.meetingId(), new MeetingRecordCallbackRequest(
                1, fixture.commandId(), TITLE, null, List.of(), List.of(), List.of()
        ))).isInstanceOf(MeetingRecordContentCodecException.class);

        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.PROCESSING);
    }

    /**
     * 요약 상태 전이는 저장보다 먼저 수행되므로, 상태 전이가 거부되면 회의록은 애초에 만들어지지 않는다.
     * generateSummary가 true인데 상태가 NOT_REQUESTED인 조합은 도메인 규칙상 만들 수 없어
     * 네이티브 UPDATE로 손상된 상태를 만든 뒤 저장이 일어나지 않는 것만 확인한다.
     */
    @DisplayName("요약 상태가 손상된 회의는 회의록을 저장하지 않는다.")
    @Test
    void doesNotSaveWhenSummaryStateIsCorrupted() {
        Fixture fixture = fixture(true);
        executeInTransaction(() -> entityManager.createNativeQuery("""
                update meeting
                set summary_status = 'NOT_REQUESTED'
                where id = :meetingId
                """).setParameter("meetingId", fixture.meetingId()).executeUpdate());

        assertBusinessError(
                () -> service.receive(fixture.meetingId(), request(fixture.commandId())),
                MeetingRecordErrorCode.MEETING_RECORD_SUMMARY_NOT_REQUESTED
        );

        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.NOT_REQUESTED);
    }

    @DisplayName("이미 실패로 확정된 요약 분석에는 성공 Callback을 저장하지 않는다.")
    @Test
    void rejectsCallbackWhenSummaryAlreadyFailed() {
        Fixture fixture = fixture(true);
        failSummaryAnalysis(fixture.meetingId());

        assertBusinessError(
                () -> service.receive(fixture.meetingId(), request(fixture.commandId())),
                MeetingRecordErrorCode.MEETING_RECORD_SUMMARY_ALREADY_FAILED
        );

        assertThat(MeetingRecordErrorCode.MEETING_RECORD_SUMMARY_ALREADY_FAILED.getStatus())
                .isEqualTo(HttpStatus.CONFLICT);
        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.FAILED);
        assertThat(publishedEvents()).isEmpty();
    }

    /**
     * MEETING_SUMMARY_READY SQS 이벤트가 Callback보다 먼저 도착해 상태만 SUCCEEDED로 바뀐 경우다.
     * 이때도 실제 회의록 본문은 Callback으로 저장되어야 한다.
     */
    @DisplayName("요약 상태가 이미 SUCCEEDED여도 회의록이 없으면 Callback은 저장에 성공한다.")
    @Test
    void savesWhenSummaryAlreadySucceededButRecordMissing() {
        Fixture fixture = fixture(true);
        executeInTransaction(() -> {
            entityManager.find(Meeting.class, fixture.meetingId()).completeSummaryAnalysis();
            return null;
        });
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.SUCCEEDED);

        MeetingRecordCallbackResponse response = service.receive(
                fixture.meetingId(), request(fixture.commandId())
        );

        assertThat(response.duplicated()).isFalse();
        assertThat(meetingRecordRepository.count()).isEqualTo(1);
        assertThat(meetingRecordRepository.findByMeetingId(fixture.meetingId()))
                .isPresent()
                .get()
                .extracting(MeetingRecord::getTitle)
                .isEqualTo(TITLE);
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.SUCCEEDED);
    }

    @DisplayName("본문 한 영역의 JSON이 TEXT 한도를 넘으면 400이고 아무것도 저장되지 않는다.")
    @ParameterizedTest
    @ValueSource(strings = {"summary", "decisions", "nextTodos", "issues"})
    void rejectsContentExceedingTextLimit(String oversizedField) {
        Fixture fixture = fixture(true);
        List<String> oversized = List.of("가".repeat(22_000));
        List<String> normal = List.of("정상 항목");
        assertThat(contentCodec.encode(oversized).getBytes(StandardCharsets.UTF_8).length)
                .isGreaterThan(65_535);

        assertBusinessError(
                () -> service.receive(fixture.meetingId(), new MeetingRecordCallbackRequest(
                        1,
                        fixture.commandId(),
                        TITLE,
                        "summary".equals(oversizedField) ? oversized : normal,
                        "decisions".equals(oversizedField) ? oversized : normal,
                        "nextTodos".equals(oversizedField) ? oversized : normal,
                        "issues".equals(oversizedField) ? oversized : normal
                )),
                MeetingRecordErrorCode.MEETING_RECORD_CONTENT_TOO_LARGE
        );

        assertThat(MeetingRecordErrorCode.MEETING_RECORD_CONTENT_TOO_LARGE.getStatus())
                .isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(publishedEvents()).isEmpty();
    }

    @DisplayName("앞 영역이 정상이어도 뒤 영역이 한도를 넘으면 어떤 회의록도 저장되지 않는다.")
    @Test
    void rejectsWhenLaterFieldExceedsTextLimit() {
        Fixture fixture = fixture(true);

        assertBusinessError(
                () -> service.receive(fixture.meetingId(), new MeetingRecordCallbackRequest(
                        1,
                        fixture.commandId(),
                        TITLE,
                        List.of("정상 요약"),
                        List.of("정상 결정"),
                        List.of("가".repeat(22_000)),
                        List.of("정상 이슈")
                )),
                MeetingRecordErrorCode.MEETING_RECORD_CONTENT_TOO_LARGE
        );

        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(publishedEvents()).isEmpty();
    }

    @DisplayName("한도 이하의 큰 본문은 정상 저장되고 UTF-8 바이트 기준을 만족한다.")
    @Test
    void savesLargeContentWithinTextLimit() {
        Fixture fixture = fixture(true);
        // 한국어 1자는 UTF-8 3바이트라 21,000자는 약 63,000바이트로 한도 이하다.
        List<String> nearLimit = List.of("가".repeat(21_000));
        String encoded = contentCodec.encode(nearLimit);
        assertThat(encoded.getBytes(StandardCharsets.UTF_8).length)
                .isGreaterThan(60_000)
                .isLessThanOrEqualTo(65_535);

        MeetingRecordCallbackResponse response = service.receive(
                fixture.meetingId(),
                new MeetingRecordCallbackRequest(
                        1, fixture.commandId(), TITLE, nearLimit, List.of(), List.of(), List.of()
                )
        );

        assertThat(response.duplicated()).isFalse();
        MeetingRecord stored = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(contentCodec.decode(stored.getSummaryJson())).isEqualTo(nearLimit);
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.SUCCEEDED);
    }

    /**
     * 저장 단계에서 예외가 나면 먼저 수행한 요약 상태 전이가 DB에 남지 않아야 한다.
     * 저장 호출만 스텁으로 실패시키며, 트랜잭션 경계와 커밋 여부는 실제 DB로 확인한다.
     */
    @DisplayName("회의록 저장이 실패하면 앞서 수행한 요약 상태 전이가 커밋되지 않는다.")
    @Test
    void doesNotCommitSummaryTransitionWhenSaveFails() {
        Fixture fixture = fixture(true);
        doThrow(new DataIntegrityViolationException("forced save failure"))
                .when(meetingRecordRepositorySpy).saveAndFlush(any(MeetingRecord.class));

        try {
            assertThatThrownBy(() -> service.receive(
                    fixture.meetingId(), request(fixture.commandId())
            )).isInstanceOf(DataIntegrityViolationException.class);
        } finally {
            reset(meetingRecordRepositorySpy);
        }

        assertThat(meetingRecordRepository.count()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(publishedEvents()).isEmpty();
    }

    @DisplayName("동시에 같은 Callback이 도착해도 회의록은 정확히 1건이고 두 요청 모두 성공한다.")
    @Test
    void concurrentIdenticalCallbacksCreateExactlyOneRecord() throws Exception {
        Fixture fixture = fixture(true);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            Future<Object> first = executor.submit(
                    () -> receiveAfterSignal(fixture, ready, start)
            );
            Future<Object> second = executor.submit(
                    () -> receiveAfterSignal(fixture, ready, start)
            );

            ready.await();
            start.countDown();
            List<Object> results = List.of(first.get(), second.get());

            assertThat(results).allMatch(MeetingRecordCallbackResponse.class::isInstance);
            assertThat(results)
                    .extracting(result -> ((MeetingRecordCallbackResponse) result).duplicated())
                    .containsExactlyInAnyOrder(false, true);
        }

        assertThat(meetingRecordRepository.count()).isEqualTo(1);
        MeetingRecord stored = meetingRecordRepository
                .findByMeetingId(fixture.meetingId())
                .orElseThrow();
        assertThat(stored.getCommandId()).isEqualTo(fixture.commandId().toString());
        assertThat(stored.getTitle()).isEqualTo(TITLE);
        assertThat(stored.getVersion()).isZero();
        assertThat(summaryStatus(fixture.meetingId())).isEqualTo(AnalysisTaskStatus.SUCCEEDED);
    }

    private Object receiveAfterSignal(
            Fixture fixture,
            CountDownLatch ready,
            CountDownLatch start
    ) throws InterruptedException {
        ready.countDown();
        start.await();
        try {
            return service.receive(fixture.meetingId(), request(fixture.commandId()));
        } catch (CustomException exception) {
            return exception.getErrorCode();
        }
    }

    private MeetingRecordCallbackRequest request(UUID commandId) {
        return new MeetingRecordCallbackRequest(
                1,
                commandId,
                TITLE,
                List.of("첫 번째 전체 요약", "두 번째 전체 요약"),
                List.of("첫 번째 결정 사항"),
                List.of("첫 번째 다음 할 일"),
                List.of("첫 번째 이슈")
        );
    }

    /**
     * 사용자가 회의록을 고친 상황을 만든다. 수정 API는 아직 없으므로 엔티티 메서드를 직접 호출한다.
     */
    private long editRecordAsUser(int meetingId) {
        return executeInTransaction(() -> {
            MeetingRecord record = entityManager.createQuery(
                            "select r from MeetingRecord r where r.meeting.id = :meetingId",
                            MeetingRecord.class
                    )
                    .setParameter("meetingId", meetingId)
                    .getSingleResult();
            record.update(
                    "사용자가 고친 제목",
                    contentCodec.encode(List.of("사용자가 고친 요약")),
                    contentCodec.encode(List.of("사용자가 고친 결정")),
                    contentCodec.encode(List.of()),
                    contentCodec.encode(List.of())
            );
            entityManager.flush();
            return record.getVersion();
        });
    }

    /**
     * 실패 Event Handler가 쓰는 도메인 메서드로 상태를 FAILED로 전이한다.
     * Reflection이나 setter로 강제 변경하지 않는다.
     */
    private void failSummaryAnalysis(int meetingId) {
        executeInTransaction(() -> {
            entityManager.find(Meeting.class, meetingId).failSummaryAnalysis();
            return null;
        });
    }

    private AnalysisTaskStatus summaryStatus(int meetingId) {
        return meetingRepository.findById(meetingId).orElseThrow().getSummaryStatus();
    }

    private Fixture fixture(boolean generateSummary) {
        return fixture(generateSummary, ROOM_NAME);
    }

    private Fixture fixture(boolean generateSummary, String roomName) {
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
        meeting.confirmAnalysisOptions(generateSummary, false);
        meeting = meetingRepository.saveAndFlush(meeting);

        UUID commandId = saveOutbox(meeting.getId(), member.getId());
        return new Fixture(meeting.getId(), member.getId(), commandId);
    }

    /**
     * 같은 회의의 분석 요청 Command를 새 commandId로 재발행한 상태를 만든다.
     * (meeting_id, command_type) UNIQUE 때문에 행을 추가할 수 없어 기존 행의 commandId를 교체한다.
     */
    private UUID reissueCommand(int meetingId) {
        UUID reissuedCommandId = UUID.randomUUID();
        executeInTransaction(() -> entityManager.createNativeQuery("""
                update meeting_analysis_command_outbox
                set command_id = :commandId
                where meeting_id = :meetingId
                """)
                .setParameter("commandId", reissuedCommandId.toString())
                .setParameter("meetingId", meetingId)
                .executeUpdate());
        return reissuedCommandId;
    }

    private UUID saveOutbox(int meetingId, int memberId) {
        UUID commandId = UUID.randomUUID();
        executeInTransaction(() -> {
            Meeting meeting = entityManager.find(Meeting.class, meetingId);
            entityManager.persist(MeetingAnalysisCommandOutbox.pending(
                    commandId,
                    meeting,
                    MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                    "{}",
                    memberId,
                    LocalDateTime.now()
            ));
            return null;
        });
        return commandId;
    }

    private Object queryInTransaction(String nativeQuery) {
        return executeInTransaction(() ->
                entityManager.createNativeQuery(nativeQuery).getSingleResult());
    }

    /**
     * 테스트 클래스에 @Transactional을 붙이지 않으므로, 준비와 검증에 필요한 영속성 작업만
     * 별도 트랜잭션으로 커밋한다. Service 호출은 자체 트랜잭션에서 독립적으로 커밋된다.
     */
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

    private List<MeetingRecordCreatedNotificationEvent> publishedEvents() {
        return applicationEvents
                .stream(MeetingRecordCreatedNotificationEvent.class)
                .toList();
    }

    private void assertBusinessError(ThrowingCallable callable, ErrorCode errorCode) {
        assertThatThrownBy(callable)
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(errorCode);
    }

    private record Fixture(int meetingId, int memberId, UUID commandId) {
    }
}
