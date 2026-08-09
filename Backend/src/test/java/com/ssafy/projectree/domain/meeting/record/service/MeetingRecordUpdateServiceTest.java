package com.ssafy.projectree.domain.meeting.record.service;

import com.ssafy.projectree.domain.meeting.entity.Meeting;
import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordUpdateRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordUpdateResponse;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.domain.meeting.record.repository.MeetingRecordRepository;
import com.ssafy.projectree.domain.meeting.repository.MeetingRepository;
import com.ssafy.projectree.domain.project.entity.Project;
import com.ssafy.projectree.domain.project.repository.ProjectMemberRepository;
import com.ssafy.projectree.domain.project.repository.ProjectRepository;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class MeetingRecordUpdateServiceTest {

    private static final int PROJECT_ID = 3;
    private static final int MEETING_ID = 35;
    private static final int MEMBER_ID = 22;

    @Mock
    private ProjectRepository projectRepository;
    @Mock
    private ProjectMemberRepository projectMemberRepository;
    @Mock
    private MeetingRepository meetingRepository;
    @Mock
    private MeetingRecordRepository meetingRecordRepository;
    @Mock
    private MeetingRecordContentEncoder contentEncoder;
    @Mock
    private Project project;
    @Mock
    private Meeting meeting;
    @Mock
    private MeetingRecord record;

    private MeetingRecordUpdateService service;

    @BeforeEach
    void setUp() {
        service = new MeetingRecordUpdateService(
                projectRepository,
                projectMemberRepository,
                meetingRepository,
                meetingRecordRepository,
                contentEncoder
        );
    }

    @DisplayName("권한과 version이 유효하면 전체 본문을 교체하고 flush 후 version을 반환한다.")
    @Test
    void updatesWholeRecord() {
        MeetingRecordUpdateRequest request = request(0L);
        LocalDateTime updatedAt = LocalDateTime.of(2026, 8, 5, 17, 0);
        MeetingRecordContentEncoder.EncodedContent encoded =
                new MeetingRecordContentEncoder.EncodedContent(
                        "[\"요약\"]",
                        "[\"결정\"]",
                        "[\"할 일\"]",
                        "[\"이슈\"]"
                );
        allowAccess();
        when(meetingRecordRepository.findByMeetingId(MEETING_ID))
                .thenReturn(Optional.of(record));
        when(record.getVersion()).thenReturn(0L, 1L);
        when(contentEncoder.encode(
                request.summary(),
                request.decisions(),
                request.nextTodos(),
                request.issues()
        )).thenReturn(encoded);
        when(meetingRecordRepository.saveAndFlush(record)).thenReturn(record);
        when(record.getId()).thenReturn(12L);
        when(record.getTitle()).thenReturn(request.title());
        when(record.getUpdatedAt()).thenReturn(updatedAt);

        MeetingRecordUpdateResponse response = service.update(
                PROJECT_ID, MEETING_ID, MEMBER_ID, request
        );

        verify(record).update(
                request.title(),
                encoded.summary(),
                encoded.decisions(),
                encoded.nextTodos(),
                encoded.issues()
        );
        verify(meetingRecordRepository).saveAndFlush(record);
        assertThat(response.version()).isEqualTo(1L);
        assertThat(response.updatedAt()).isEqualTo(updatedAt);
        assertThat(response.summary()).containsExactly("요약");
    }

    @DisplayName("stale version이면 본문을 인코딩하거나 엔티티를 수정하지 않는다.")
    @Test
    void rejectsStaleVersionWithoutMutation() {
        MeetingRecordUpdateRequest request = request(0L);
        allowAccess();
        when(meetingRecordRepository.findByMeetingId(MEETING_ID))
                .thenReturn(Optional.of(record));
        when(record.getVersion()).thenReturn(1L);

        assertError(
                () -> service.update(PROJECT_ID, MEETING_ID, MEMBER_ID, request),
                MeetingRecordErrorCode.MEETING_RECORD_VERSION_CONFLICT
        );

        verify(contentEncoder, never()).encode(
                request.summary(),
                request.decisions(),
                request.nextTodos(),
                request.issues()
        );
        verify(meetingRecordRepository, never()).saveAndFlush(record);
    }

    @DisplayName("미래 version도 version conflict로 거부한다.")
    @Test
    void rejectsFutureVersion() {
        allowAccess();
        when(meetingRecordRepository.findByMeetingId(MEETING_ID))
                .thenReturn(Optional.of(record));
        when(record.getVersion()).thenReturn(0L);

        assertError(
                () -> service.update(PROJECT_ID, MEETING_ID, MEMBER_ID, request(10L)),
                MeetingRecordErrorCode.MEETING_RECORD_VERSION_CONFLICT
        );
    }

    @DisplayName("프로젝트 멤버라도 회의 생성자가 아니면 수정을 거부한다.")
    @Test
    void rejectsNonCreator() {
        when(projectRepository.existsById(PROJECT_ID)).thenReturn(true);
        when(projectMemberRepository.existsByProjectIdAndMemberId(PROJECT_ID, MEMBER_ID))
                .thenReturn(true);
        when(meetingRepository.findByIdWithProject(MEETING_ID))
                .thenReturn(Optional.of(meeting));
        when(meeting.getProject()).thenReturn(project);
        when(project.getId()).thenReturn(PROJECT_ID);
        when(meeting.getCreatorMemberId()).thenReturn(999);

        assertError(
                () -> service.update(PROJECT_ID, MEETING_ID, MEMBER_ID, request(0L)),
                MeetingRecordErrorCode.MEETING_RECORD_UPDATE_FORBIDDEN
        );

        verify(meetingRecordRepository, never()).findByMeetingId(MEETING_ID);
    }

    @DisplayName("프로젝트가 없으면 가장 먼저 PROJECT_NOT_FOUND를 반환한다.")
    @Test
    void rejectsMissingProjectFirst() {
        when(projectRepository.existsById(PROJECT_ID)).thenReturn(false);

        assertError(
                () -> service.update(PROJECT_ID, MEETING_ID, MEMBER_ID, request(0L)),
                ProjectErrorCode.PROJECT_NOT_FOUND
        );

        verify(projectMemberRepository, never())
                .existsByProjectIdAndMemberId(PROJECT_ID, MEMBER_ID);
        verify(meetingRepository, never()).findByIdWithProject(MEETING_ID);
    }

    private void allowAccess() {
        when(projectRepository.existsById(PROJECT_ID)).thenReturn(true);
        when(projectMemberRepository.existsByProjectIdAndMemberId(PROJECT_ID, MEMBER_ID))
                .thenReturn(true);
        when(meetingRepository.findByIdWithProject(MEETING_ID))
                .thenReturn(Optional.of(meeting));
        when(meeting.getProject()).thenReturn(project);
        when(project.getId()).thenReturn(PROJECT_ID);
        when(meeting.getCreatorMemberId()).thenReturn(MEMBER_ID);
    }

    private MeetingRecordUpdateRequest request(long version) {
        return new MeetingRecordUpdateRequest(
                "수정 제목",
                List.of("요약"),
                List.of("결정"),
                List.of("할 일"),
                List.of("이슈"),
                version
        );
    }

    private void assertError(
            org.assertj.core.api.ThrowableAssert.ThrowingCallable callable,
            Object expected
    ) {
        assertThatThrownBy(callable)
                .isInstanceOf(CustomException.class)
                .extracting(exception -> ((CustomException) exception).getErrorCode())
                .isEqualTo(expected);
    }
}
