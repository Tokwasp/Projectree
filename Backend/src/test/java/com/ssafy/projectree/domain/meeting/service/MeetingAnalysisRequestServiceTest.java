package com.ssafy.projectree.domain.meeting.service;

import com.ssafy.projectree.domain.meeting.command.MeetingAnalysisRequestedCommand;
import com.ssafy.projectree.domain.meeting.dto.request.MeetingAnalysisRequest;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisCommandOutbox;
import com.ssafy.projectree.domain.meeting.outbox.entity.MeetingAnalysisOutboxStatus;
import com.ssafy.projectree.domain.meeting.outbox.repository.MeetingAnalysisCommandOutboxRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.test.util.ReflectionTestUtils;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.ObjectMapper;

import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MeetingAnalysisRequestServiceTest {

    private static final int PROJECT_ID = 15;
    private static final int MEMBER_ID = 7;
    private static final int MEETING_ID = 35;
    private static final String ROOM_NAME = "c6db7ac7-d3c7-4f18-928c-ce376ccfabba";

    @Mock
    private MeetingRepository meetingRepository;

    @Mock
    private ProjectMemberRepository projectMemberRepository;

    @Mock
    private MeetingAnalysisCommandOutboxRepository outboxRepository;

    @Mock
    private ObjectMapper objectMapper;

    private MeetingAnalysisRequestService service;

    @BeforeEach
    void setUp() {
        service = new MeetingAnalysisRequestService(
                meetingRepository,
                projectMemberRepository,
                outboxRepository,
                objectMapper
        );
    }

    @DisplayName("??媛吏 ?듭뀡 議고빀???뺤젙?섍퀬 PENDING Outbox瑜???ν븳??")
    @ParameterizedTest
    @CsvSource({
            "true, true, PROCESSING, PROCESSING",
            "true, false, PROCESSING, SKIPPED",
            "false, true, SKIPPED, PROCESSING",
            "false, false, SKIPPED, SKIPPED"
    })
    void confirmsOptionsAndSavesOutbox(
            boolean generateSummary,
            boolean generateNodes,
            AnalysisTaskStatus expectedSummaryStatus,
            AnalysisTaskStatus expectedNodeStatus
    ) {
        Meeting meeting = meeting();
        when(meetingRepository.findByProjectIdAndRoomNameForUpdate(PROJECT_ID, ROOM_NAME))
                .thenReturn(Optional.of(meeting));
        when(projectMemberRepository.existsByProjectIdAndMemberId(PROJECT_ID, MEMBER_ID))
                .thenReturn(true);
        when(objectMapper.writeValueAsString(any(MeetingAnalysisRequestedCommand.class)))
                .thenReturn("{\"commandSchemaVersion\":1}");

        var response = service.requestAnalysis(
                PROJECT_ID,
                ROOM_NAME,
                MEMBER_ID,
                new MeetingAnalysisRequest(generateSummary, generateNodes)
        );

        assertThat(meeting.isGenerateSummary()).isEqualTo(generateSummary);
        assertThat(meeting.getSummaryStatus()).isEqualTo(expectedSummaryStatus);
        assertThat(meeting.isGenerateNodes()).isEqualTo(generateNodes);
        assertThat(meeting.getNodeStatus()).isEqualTo(expectedNodeStatus);
        assertThat(meeting.isAnalysisRequestConfirmed()).isTrue();
        assertThat(response.commandId()).isNotNull();

        ArgumentCaptor<MeetingAnalysisCommandOutbox> captor =
                ArgumentCaptor.forClass(MeetingAnalysisCommandOutbox.class);
        verify(outboxRepository).saveAndFlush(captor.capture());
        MeetingAnalysisCommandOutbox outbox = captor.getValue();
        assertThat(outbox.getMeeting()).isSameAs(meeting);
        assertThat(outbox.getStatus()).isEqualTo(MeetingAnalysisOutboxStatus.PENDING);
        assertThat(outbox.getAttemptCount()).isZero();
        assertThat(outbox.getPublishedAt()).isNull();
        assertThat(outbox.getLastError()).isNull();
        assertThat(outbox.getCommandId()).isEqualTo(response.commandId().toString());
    }

    @DisplayName("Meeting???놁쑝硫?404 ?ㅻ쪟瑜?諛쒖깮?쒗궎怨?Outbox瑜???ν븯吏 ?딅뒗??")
    @Test
    void meetingNotFound() {
        when(meetingRepository.findByProjectIdAndRoomNameForUpdate(PROJECT_ID, ROOM_NAME))
                .thenReturn(Optional.empty());

        assertError(
                () -> service.requestAnalysis(
                        PROJECT_ID, ROOM_NAME, MEMBER_ID, new MeetingAnalysisRequest(true, false)
                ),
                MeetingErrorCode.MEETING_NOT_FOUND
        );
        verify(outboxRepository, never()).saveAndFlush(any());
    }

    @DisplayName("Project 硫ㅻ쾭媛 ?꾨땲硫?403 ?ㅻ쪟瑜?諛쒖깮?쒗궓??")
    @Test
    void accessDenied() {
        Meeting meeting = meeting();
        when(meetingRepository.findByProjectIdAndRoomNameForUpdate(PROJECT_ID, ROOM_NAME))
                .thenReturn(Optional.of(meeting));
        when(projectMemberRepository.existsByProjectIdAndMemberId(PROJECT_ID, MEMBER_ID))
                .thenReturn(false);

        assertError(
                () -> service.requestAnalysis(
                        PROJECT_ID, ROOM_NAME, MEMBER_ID, new MeetingAnalysisRequest(true, false)
                ),
                MeetingErrorCode.MEETING_ACCESS_DENIED
        );
        assertThat(meeting.isAnalysisRequestConfirmed()).isFalse();
        verify(outboxRepository, never()).saveAndFlush(any());
    }

    @DisplayName("?대? ?뺤젙??遺꾩꽍 ?붿껌? ?듭뀡怨?Outbox瑜?蹂寃쏀븯吏 ?딅뒗??")
    @Test
    void alreadyRequested() {
        Meeting meeting = meeting();
        meeting.confirmAnalysisOptions(true, false);
        when(meetingRepository.findByProjectIdAndRoomNameForUpdate(PROJECT_ID, ROOM_NAME))
                .thenReturn(Optional.of(meeting));
        when(projectMemberRepository.existsByProjectIdAndMemberId(PROJECT_ID, MEMBER_ID))
                .thenReturn(true);

        assertError(
                () -> service.requestAnalysis(
                        PROJECT_ID, ROOM_NAME, MEMBER_ID, new MeetingAnalysisRequest(false, true)
                ),
                MeetingErrorCode.MEETING_ANALYSIS_ALREADY_REQUESTED
        );
        assertThat(meeting.isGenerateSummary()).isTrue();
        assertThat(meeting.getSummaryStatus()).isEqualTo(AnalysisTaskStatus.PROCESSING);
        assertThat(meeting.isGenerateNodes()).isFalse();
        assertThat(meeting.getNodeStatus()).isEqualTo(AnalysisTaskStatus.SKIPPED);
        verify(outboxRepository, never()).saveAndFlush(any());
    }

    @DisplayName("理쒖쥌 FAILED ?곹깭?먯꽌???ъ슂泥?븷 ???녿떎.")
    @Test
    void failedStatusCannotBeRequestedAgain() {
        Meeting meeting = meeting();
        meeting.confirmAnalysisOptions(true, true);
        meeting.markSummaryFailed();
        meeting.markNodesFailed();
        when(meetingRepository.findByProjectIdAndRoomNameForUpdate(PROJECT_ID, ROOM_NAME))
                .thenReturn(Optional.of(meeting));
        when(projectMemberRepository.existsByProjectIdAndMemberId(PROJECT_ID, MEMBER_ID))
                .thenReturn(true);

        assertError(
                () -> service.requestAnalysis(
                        PROJECT_ID, ROOM_NAME, MEMBER_ID, new MeetingAnalysisRequest(true, true)
                ),
                MeetingErrorCode.MEETING_ANALYSIS_ALREADY_REQUESTED
        );
    }

    @DisplayName("?섎せ??roomName怨??꾨씫??Boolean? Repository 議고쉶 ?꾩뿉 嫄곗젅?쒕떎.")
    @Test
    void validatesInputBeforeLockQuery() {
        assertError(
                () -> service.requestAnalysis(
                        PROJECT_ID, "1-1-1-1-1", MEMBER_ID, new MeetingAnalysisRequest(true, false)
                ),
                MeetingErrorCode.INVALID_ROOM_NAME
        );
        assertError(
                () -> service.requestAnalysis(
                        PROJECT_ID, ROOM_NAME, MEMBER_ID, new MeetingAnalysisRequest(null, false)
                ),
                CommonErrorCode.INVALID_REQUEST
        );
        verify(meetingRepository, never())
                .findByProjectIdAndRoomNameForUpdate(any(Integer.class), any());
    }

    @DisplayName("?臾몄옄 canonical UUID???뚮Ц?먮줈 ?뺢퇋?뷀븳 ??Repository?먯꽌 議고쉶?쒕떎.")
    @Test
    void serializationFailure() {
        Meeting meeting = meeting();
        when(meetingRepository.findByProjectIdAndRoomNameForUpdate(PROJECT_ID, ROOM_NAME))
                .thenReturn(Optional.of(meeting));
        when(projectMemberRepository.existsByProjectIdAndMemberId(PROJECT_ID, MEMBER_ID))
                .thenReturn(true);
        when(objectMapper.writeValueAsString(any(MeetingAnalysisRequestedCommand.class)))
                .thenThrow(mock(JacksonException.class));

        assertError(
                () -> service.requestAnalysis(
                        PROJECT_ID, ROOM_NAME, MEMBER_ID, new MeetingAnalysisRequest(true, false)
                ),
                MeetingErrorCode.OUTBOX_SERIALIZATION_FAILED
        );
        verify(outboxRepository, never()).saveAndFlush(any());
    }

    private Meeting meeting() {
        Project project = Project.builder().title("project").content("content").build();
        ReflectionTestUtils.setField(project, "id", PROJECT_ID);
        Meeting meeting = Meeting.create(project, ROOM_NAME);
        ReflectionTestUtils.setField(meeting, "id", MEETING_ID);
        return meeting;
    }

    private void assertError(
            org.assertj.core.api.ThrowableAssert.ThrowingCallable callable,
            com.ssafy.projectree.global.exception.ErrorCode errorCode
    ) {
        assertThatThrownBy(callable)
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(errorCode);
    }
}
