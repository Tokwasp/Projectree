package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisCommandType;
import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisRequestedCommand;
import com.ssafy.projectree.domain.meeting.dto.request.MeetingAnalysisRequest;
import com.ssafy.projectree.domain.meeting.dto.response.MeetingAnalysisRequestResponse;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.member.Member;
import com.ssafy.projectree.domain.member.repository.MemberRepository;
import com.ssafy.projectree.domain.member.service.GoogleOAuthClient;
import com.ssafy.projectree.domain.member.service.NaverOAuthClient;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.entity.ProjectMember;
import com.ssafy.projectree.domain.project.entity.ProjectRole;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.EnumSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.util.ReflectionTestUtils;
import tools.jackson.databind.ObjectMapper;

import java.time.Instant;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ActiveProfiles("test")
@SpringBootTest
class MeetingAnalysisRequestIntegrationTest {

    private static final String ROOM_NAME = "c6db7ac7-d3c7-4f18-928c-ce376ccfabba";

    @MockitoBean
    private GoogleOAuthClient googleOAuthClient;

    @MockitoBean
    private NaverOAuthClient naverOAuthClient;

    @Autowired
    private MeetingAnalysisRequestService service;

    @Autowired
    private MeetingRepository meetingRepository;

    @Autowired
    private MeetingAnalysisCommandOutboxRepository outboxRepository;

    @Autowired
    private ProjectRepository projectRepository;

    @Autowired
    private ProjectMemberRepository projectMemberRepository;

    @Autowired
    private MemberRepository memberRepository;

    @Autowired
    private ObjectMapper objectMapper;

    @AfterEach
    void cleanUp() {
        outboxRepository.deleteAll();
        meetingRepository.deleteAll();
        projectRepository.deleteAll();
        memberRepository.deleteAll();
    }

    @DisplayName("??媛吏 ?듭뀡 議고빀??Meeting怨?Command Payload???먯옄?곸쑝濡?諛섏쁺?쒕떎.")
    @ParameterizedTest
    @CsvSource({
            "true, true, PROCESSING, PROCESSING",
            "true, false, PROCESSING, SKIPPED",
            "false, true, SKIPPED, PROCESSING",
            "false, false, SKIPPED, SKIPPED"
    })
    void savesMeetingAndCommandAtomically(
            boolean generateSummary,
            boolean generateNodes,
            AnalysisTaskStatus expectedSummaryStatus,
            AnalysisTaskStatus expectedNodeStatus
    ) {
        Fixture fixture = fixture(ProjectRole.OWNER, ROOM_NAME);
        Instant before = Instant.now();

        MeetingAnalysisRequestResponse response = service.requestAnalysis(
                fixture.projectId(),
                ROOM_NAME,
                fixture.memberId(),
                new MeetingAnalysisRequest(generateSummary, generateNodes)
        );
        Instant after = Instant.now();

        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        assertThat(meeting.isGenerateSummary()).isEqualTo(generateSummary);
        assertThat(meeting.getSummaryStatus()).isEqualTo(expectedSummaryStatus);
        assertThat(meeting.isGenerateNodes()).isEqualTo(generateNodes);
        assertThat(meeting.getNodeStatus()).isEqualTo(expectedNodeStatus);
        assertThat(meeting.isAnalysisRequestConfirmed()).isTrue();

        MeetingAnalysisCommandOutbox outbox = outboxRepository
                .findByMeetingIdAndCommandType(
                        fixture.meetingId(),
                        MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED
                )
                .orElseThrow();
        assertThat(outbox.getCommandId()).isEqualTo(response.commandId().toString());
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PENDING);
        assertThat(outbox.getAttemptCount()).isZero();
        assertThat(outbox.getRequestedByMemberId()).isEqualTo(fixture.memberId());
        assertThat(outbox.getNextAttemptAt()).isNotNull();
        assertThat(outbox.getLeaseUntil()).isNull();
        assertThat(outbox.getClaimToken()).isNull();
        assertThat(outbox.getPublishedAt()).isNull();
        assertThat(outbox.getLastError()).isNull();
        assertThat(outbox.getCreatedAt()).isNotNull();
        assertThat(outbox.getUpdatedAt()).isNotNull();

        MeetingAnalysisRequestedCommand command = objectMapper.readValue(
                outbox.getPayload(),
                MeetingAnalysisRequestedCommand.class
        );
        var payloadTree = objectMapper.readTree(outbox.getPayload());
        assertThat(command.commandSchemaVersion())
                .isEqualTo(MeetingAnalysisRequestedCommand.CURRENT_SCHEMA_VERSION);
        assertThat(command.commandId()).isEqualTo(response.commandId());
        assertThat(command.commandType())
                .isEqualTo(MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED);
        assertThat(command.requestedAt()).isBetween(before, after);
        assertThat(command.requestedAt().toString()).endsWith("Z");
        assertThat(payloadTree.path("requestedAt").isString()).isTrue();
        assertThat(payloadTree.path("requestedAt").stringValue()).endsWith("Z");
        assertThat(payloadTree.has("requestedByMemberId")).isFalse();
        assertThat(payloadTree.has("creator")).isFalse();
        assertThat(payloadTree.has("creatorMemberId")).isFalse();
        assertThat(payloadTree.path("payload").has("creator")).isFalse();
        assertThat(payloadTree.path("payload").has("creatorMemberId")).isFalse();
        assertThat(command.projectId()).isEqualTo(fixture.projectId());
        assertThat(command.payload().meetingId()).isEqualTo(fixture.meetingId());
        assertThat(command.payload().roomName()).isEqualTo(ROOM_NAME);
        assertThat(command.payload().generateSummary()).isEqualTo(generateSummary);
        assertThat(command.payload().generateNodes()).isEqualTo(generateNodes);
    }

    @DisplayName("OWNER? MEMBER 紐⑤몢 遺꾩꽍 ?붿껌???뺤젙?????덈떎.")
    @ParameterizedTest
    @EnumSource(ProjectRole.class)
    void projectMembersCanRequest(ProjectRole role) {
        Fixture fixture = fixture(role, ROOM_NAME);

        MeetingAnalysisRequestResponse response = service.requestAnalysis(
                fixture.projectId(),
                ROOM_NAME,
                fixture.memberId(),
                new MeetingAnalysisRequest(true, false)
        );

        assertThat(response.meetingId()).isEqualTo(fixture.meetingId());
        assertThat(outboxRepository.countByMeetingId(fixture.meetingId())).isEqualTo(1);
    }

    @DisplayName("프로젝트 구성원이더라도 Meeting 생성자가 아니면 분석을 요청할 수 없다.")
    @ParameterizedTest
    @EnumSource(ProjectRole.class)
    void nonCreatorProjectMemberCannotRequest(ProjectRole role) {
        Fixture fixture = fixture(ProjectRole.OWNER, ROOM_NAME);
        Member nonCreator = memberRepository.saveAndFlush(
                Member.builder()
                        .email("non-creator-" + UUID.randomUUID() + "@example.com")
                        .name("non-creator")
                        .build()
        );
        Project project = projectRepository.findById(fixture.projectId()).orElseThrow();
        ProjectMember projectMember = ProjectMember.createMember(nonCreator.getId(), role);
        projectMember.assignProject(project);
        projectMemberRepository.saveAndFlush(projectMember);

        assertBusinessError(
                () -> service.requestAnalysis(
                        fixture.projectId(),
                        ROOM_NAME,
                        nonCreator.getId(),
                        new MeetingAnalysisRequest(true, true)
                ),
                MeetingErrorCode.MEETING_ANALYSIS_CREATOR_ONLY
        );

        assertNotRequested(fixture.meetingId());
        assertThat(outboxRepository.countByMeetingId(fixture.meetingId())).isZero();
    }

    @DisplayName("레거시 Meeting에 생성자가 등록되지 않았으면 분석 요청을 확정하지 않는다.")
    @Test
    void meetingWithoutRegisteredCreatorCannotRequest() {
        Fixture fixture = fixture(ProjectRole.OWNER, ROOM_NAME);
        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        ReflectionTestUtils.setField(meeting, "creatorMemberId", null);
        meetingRepository.saveAndFlush(meeting);

        assertBusinessError(
                () -> service.requestAnalysis(
                        fixture.projectId(),
                        ROOM_NAME,
                        fixture.memberId(),
                        new MeetingAnalysisRequest(true, true)
                ),
                MeetingErrorCode.MEETING_CREATOR_NOT_REGISTERED
        );

        assertNotRequested(fixture.meetingId());
        assertThat(outboxRepository.countByMeetingId(fixture.meetingId())).isZero();
    }

    @DisplayName("?꾨줈?앺듃 硫ㅻ쾭媛 ?꾨땲硫?Meeting怨?Outbox瑜?蹂寃쏀븯吏 ?딅뒗??")
    @Test
    void outsiderCannotRequest() {
        Fixture fixture = fixture(ProjectRole.OWNER, ROOM_NAME);
        Member outsider = memberRepository.saveAndFlush(
                Member.builder().email("outsider@example.com").name("outsider").build()
        );

        assertBusinessError(
                () -> service.requestAnalysis(
                        fixture.projectId(),
                        ROOM_NAME,
                        outsider.getId(),
                        new MeetingAnalysisRequest(true, false)
                ),
                MeetingErrorCode.MEETING_ACCESS_DENIED
        );

        assertNotRequested(fixture.meetingId());
        assertThat(outboxRepository.countByMeetingId(fixture.meetingId())).isZero();
    }

    @DisplayName("projectId媛 ?ㅻⅤ硫?roomName???쇱튂?대룄 Meeting??李얠? ?딅뒗??")
    @Test
    void projectAndRoomNameMustBothMatch() {
        Fixture fixture = fixture(ProjectRole.OWNER, ROOM_NAME);
        Project otherProject = projectRepository.saveAndFlush(
                Project.builder().title("other").content("content").build()
        );

        assertBusinessError(
                () -> service.requestAnalysis(
                        otherProject.getId(),
                        ROOM_NAME,
                        fixture.memberId(),
                        new MeetingAnalysisRequest(true, false)
                ),
                MeetingErrorCode.MEETING_NOT_FOUND
        );
        assertNotRequested(fixture.meetingId());
    }

    @DisplayName("?臾몄옄 UUID ?붿껌? ?뚮Ц??DB roomName??議고쉶?섍퀬 Payload?먮룄 ?뚮Ц?먮? ??ν븳??")
    @Test
    void sequentialDuplicateRequest() {
        Fixture fixture = fixture(ProjectRole.OWNER, ROOM_NAME);
        service.requestAnalysis(
                fixture.projectId(),
                ROOM_NAME,
                fixture.memberId(),
                new MeetingAnalysisRequest(false, false)
        );

        assertBusinessError(
                () -> service.requestAnalysis(
                        fixture.projectId(),
                        ROOM_NAME,
                        fixture.memberId(),
                        new MeetingAnalysisRequest(true, true)
                ),
                MeetingErrorCode.MEETING_ANALYSIS_ALREADY_REQUESTED
        );

        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        assertThat(meeting.isGenerateSummary()).isFalse();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.SKIPPED);
        assertThat(meeting.isGenerateNodes()).isFalse();
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.SKIPPED);
        assertThat(outboxRepository.countByMeetingId(fixture.meetingId())).isEqualTo(1);
    }

    @DisplayName("?숈떆???ㅻⅨ ?듭뀡???붿껌?대룄 ???붿껌留??깃났?섍퀬 Outbox??1嫄댁씠??")
    @Test
    void concurrentRequestsAllowOnlyOneSuccess() throws Exception {
        Fixture fixture = fixture(ProjectRole.OWNER, ROOM_NAME);
        CountDownLatch ready = new CountDownLatch(2);
        CountDownLatch start = new CountDownLatch(1);

        try (ExecutorService executor = Executors.newFixedThreadPool(2)) {
            Future<Object> first = executor.submit(() -> requestAfterSignal(
                    fixture,
                    new MeetingAnalysisRequest(true, false),
                    ready,
                    start
            ));
            Future<Object> second = executor.submit(() -> requestAfterSignal(
                    fixture,
                    new MeetingAnalysisRequest(false, true),
                    ready,
                    start
            ));

            ready.await();
            start.countDown();
            List<Object> results = List.of(first.get(), second.get());

            assertThat(results.stream().filter(MeetingAnalysisRequestResponse.class::isInstance))
                    .hasSize(1);
            assertThat(results).contains(MeetingErrorCode.MEETING_ANALYSIS_ALREADY_REQUESTED);
        }

        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        MeetingAnalysisCommandOutbox outbox = outboxRepository
                .findByMeetingIdAndCommandType(
                        fixture.meetingId(),
                        MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED
                )
                .orElseThrow();
        MeetingAnalysisRequestedCommand command = objectMapper.readValue(
                outbox.getPayload(),
                MeetingAnalysisRequestedCommand.class
        );
        assertThat(outboxRepository.countByMeetingId(fixture.meetingId())).isEqualTo(1);
        assertThat(command.payload().generateSummary()).isEqualTo(meeting.isGenerateSummary());
        assertThat(command.payload().generateNodes()).isEqualTo(meeting.isGenerateNodes());
    }

    @DisplayName("Outbox UNIQUE ????ㅽ뙣 ??Meeting ?듭뀡 蹂寃쎈룄 濡ㅻ갚?쒕떎.")
    @Test
    void outboxFailureRollsBackMeetingChanges() {
        Fixture fixture = fixture(ProjectRole.OWNER, ROOM_NAME);
        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        outboxRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pending(
                        UUID.randomUUID(),
                        meeting,
                        MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                        "{}",
                        fixture.memberId(),
                        LocalDateTime.now()
                )
        );

        assertThatThrownBy(() -> service.requestAnalysis(
                fixture.projectId(),
                ROOM_NAME,
                fixture.memberId(),
                new MeetingAnalysisRequest(true, true)
        )).isInstanceOf(DataIntegrityViolationException.class);

        assertNotRequested(fixture.meetingId());
        assertThat(outboxRepository.countByMeetingId(fixture.meetingId())).isEqualTo(1);
    }

    @DisplayName("commandId UNIQUE ?쒖빟? ?쒕줈 ?ㅻⅨ Meeting??以묐났 Command ID??李⑤떒?쒕떎.")
    @Test
    void commandIdMustBeUnique() {
        Fixture first = fixture(
                ProjectRole.OWNER,
                "c6db7ac7-d3c7-4f18-928c-ce376ccfabba"
        );
        Fixture second = fixture(
                ProjectRole.OWNER,
                "550e8400-e29b-41d4-a716-446655440000"
        );
        UUID commandId = UUID.randomUUID();
        Meeting firstMeeting = meetingRepository.findById(first.meetingId()).orElseThrow();
        Meeting secondMeeting = meetingRepository.findById(second.meetingId()).orElseThrow();
        outboxRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pending(
                        commandId,
                        firstMeeting,
                        MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                        "{}",
                        first.memberId(),
                        LocalDateTime.now()
                )
        );

        assertThatThrownBy(() -> outboxRepository.saveAndFlush(
                MeetingAnalysisCommandOutbox.pending(
                        commandId,
                        secondMeeting,
                        MeetingAnalysisCommandType.MEETING_ANALYSIS_REQUESTED,
                        "{}",
                        second.memberId(),
                        LocalDateTime.now()
                )
        )).isInstanceOf(DataIntegrityViolationException.class);
    }

    private Object requestAfterSignal(
            Fixture fixture,
            MeetingAnalysisRequest request,
            CountDownLatch ready,
            CountDownLatch start
    ) throws InterruptedException {
        ready.countDown();
        start.await();
        try {
            return service.requestAnalysis(
                    fixture.projectId(),
                    ROOM_NAME,
                    fixture.memberId(),
                    request
            );
        } catch (CustomException exception) {
            return exception.getErrorCode();
        }
    }

    @Test
    void uppercaseRoomNameIsCanonicalized() {
        Fixture fixture = fixture(ProjectRole.OWNER, ROOM_NAME);

        service.requestAnalysis(
                fixture.projectId(), ROOM_NAME.toUpperCase(), fixture.memberId(),
                new MeetingAnalysisRequest(true, false)
        );

        Meeting meeting = meetingRepository.findById(fixture.meetingId()).orElseThrow();
        assertThat(meeting.getRoomName()).isEqualTo(ROOM_NAME);
        MeetingAnalysisCommandOutbox outbox = outboxRepository.findAll().get(0);
        assertThat(outbox.getPayload()).contains(ROOM_NAME);
    }

    private Fixture fixture(ProjectRole role, String roomName) {
        String suffix = UUID.randomUUID().toString();
        Member member = memberRepository.saveAndFlush(
                Member.builder()
                        .email("member-" + suffix + "@example.com")
                        .name("member")
                        .build()
        );
        Project project = Project.builder().title("project").content("content").build();
        ProjectMember creator = ProjectMember.createMember(member.getId(), role);
        project.addMember(creator);
        project = projectRepository.saveAndFlush(project);
        Meeting meeting = meetingRepository.saveAndFlush(
                Meeting.create(project, creator, roomName)
        );
        return new Fixture(project.getId(), member.getId(), meeting.getId());
    }

    private void assertNotRequested(int meetingId) {
        Meeting meeting = meetingRepository.findById(meetingId).orElseThrow();
        assertThat(meeting.isGenerateSummary()).isFalse();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.NOT_REQUESTED);
        assertThat(meeting.isGenerateNodes()).isFalse();
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.NOT_REQUESTED);
    }

    private void assertBusinessError(
            org.assertj.core.api.ThrowableAssert.ThrowingCallable callable,
            MeetingErrorCode errorCode
    ) {
        assertThatThrownBy(callable)
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(errorCode);
    }

    private record Fixture(int projectId, int memberId, int meetingId) {
    }
}
