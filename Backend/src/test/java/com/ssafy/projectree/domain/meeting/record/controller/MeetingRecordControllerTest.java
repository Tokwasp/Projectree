package com.ssafy.projectree.domain.meeting.record.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordDetailResponse;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.config.session.SessionConst;
import com.ssafy.projectree.global.exception.CustomException;
import com.ssafy.projectree.global.exception.ProjectErrorCode;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpSession;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.List;

import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class MeetingRecordControllerTest extends ControllerTestSupport {

    private static final int PROJECT_ID = 3;
    private static final int MEETING_ID = 35;
    private static final int MEMBER_ID = 22;
    private static final long MEETING_RECORD_ID = 12L;
    private static final String URI = "/api/projects/{projectId}/meetings/{meetingId}/record";
    private static final LocalDateTime STARTED_AT = LocalDateTime.of(2026, 8, 5, 15, 0, 0);
    private static final LocalDateTime ENDED_AT = LocalDateTime.of(2026, 8, 5, 16, 31, 0);
    private static final LocalDateTime RECORD_CREATED_AT = LocalDateTime.of(2026, 8, 5, 16, 35, 0);

    @DisplayName("회의록 상세를 조회하면 200과 함께 모든 응답 필드를 반환한다.")
    @Test
    void getRecord() throws Exception {
        when(meetingRecordQueryService.getRecord(PROJECT_ID, MEETING_ID, MEMBER_ID))
                .thenReturn(response());

        mockMvc.perform(get(URI, PROJECT_ID, MEETING_ID).session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data.meetingRecordId").value(MEETING_RECORD_ID))
                .andExpect(jsonPath("$.data.projectId").value(PROJECT_ID))
                .andExpect(jsonPath("$.data.meetingId").value(MEETING_ID))
                .andExpect(jsonPath("$.data.title")
                        .value("AI 노드 구조 및 CI/CD 파이프라인 구축 방안 논의"))
                .andExpect(jsonPath("$.data.meetingDate").value("2026-08-05"))
                .andExpect(jsonPath("$.data.startedAt").value("2026-08-05T15:00:00"))
                .andExpect(jsonPath("$.data.endedAt").value("2026-08-05T16:31:00"))
                .andExpect(jsonPath("$.data.durationMinutes").value(91))
                .andExpect(jsonPath("$.data.summary.length()").value(1))
                .andExpect(jsonPath("$.data.summary[0]")
                        .value("회의록 자동 생성 품질을 검토했습니다."))
                .andExpect(jsonPath("$.data.decisions[0]")
                        .value("CI/CD 파이프라인을 단순화하기로 했습니다."))
                .andExpect(jsonPath("$.data.nextTodos[0]")
                        .value("기술 용어 사전 목록을 설계합니다."))
                .andExpect(jsonPath("$.data.issues[0]")
                        .value("전문 용어 변환 오류가 있습니다."))
                .andExpect(jsonPath("$.data.version").value(0))
                .andExpect(jsonPath("$.data.createdAt").value("2026-08-05T16:35:00"))
                .andExpect(jsonPath("$.data.updatedAt").value("2026-08-05T16:35:00"));

        verify(meetingRecordQueryService).getRecord(PROJECT_ID, MEETING_ID, MEMBER_ID);
    }

    @DisplayName("PathVariable과 로그인 사용자 ID가 Query Service로 그대로 전달된다.")
    @Test
    void passesPathVariablesAndLoginMemberId() throws Exception {
        when(meetingRecordQueryService.getRecord(7, 99, MEMBER_ID)).thenReturn(response());

        mockMvc.perform(get(URI, 7, 99).session(loginSession()))
                .andExpect(status().isOk());

        verify(meetingRecordQueryService).getRecord(7, 99, MEMBER_ID);
    }

    @DisplayName("본문이 비어 있으면 네 영역 모두 빈 배열로 응답한다.")
    @Test
    void getRecordWithEmptyContent() throws Exception {
        when(meetingRecordQueryService.getRecord(PROJECT_ID, MEETING_ID, MEMBER_ID))
                .thenReturn(new MeetingRecordDetailResponse(
                        MEETING_RECORD_ID,
                        PROJECT_ID,
                        MEETING_ID,
                        "제목",
                        STARTED_AT.toLocalDate(),
                        STARTED_AT,
                        STARTED_AT,
                        0L,
                        List.of(),
                        List.of(),
                        List.of(),
                        List.of(),
                        0L,
                        RECORD_CREATED_AT,
                        RECORD_CREATED_AT
                ));

        mockMvc.perform(get(URI, PROJECT_ID, MEETING_ID).session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.summary").isArray())
                .andExpect(jsonPath("$.data.summary.length()").value(0))
                .andExpect(jsonPath("$.data.decisions.length()").value(0))
                .andExpect(jsonPath("$.data.nextTodos.length()").value(0))
                .andExpect(jsonPath("$.data.issues.length()").value(0))
                .andExpect(jsonPath("$.data.durationMinutes").value(0));
    }

    @DisplayName("회의록이 없으면 404와 MEETING_RECORD_NOT_FOUND를 반환한다.")
    @Test
    void returnsNotFoundWhenRecordIsMissing() throws Exception {
        when(meetingRecordQueryService.getRecord(PROJECT_ID, MEETING_ID, MEMBER_ID))
                .thenThrow(new CustomException(MeetingRecordErrorCode.MEETING_RECORD_NOT_FOUND));

        mockMvc.perform(get(URI, PROJECT_ID, MEETING_ID).session(loginSession()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode").value("MEETING_RECORD_NOT_FOUND"));
    }

    @DisplayName("프로젝트 멤버가 아니면 404와 PROJECT_PARTICIPANT_NOT_FOUND를 반환한다.")
    @Test
    void returnsNotFoundWhenRequesterIsNotProjectMember() throws Exception {
        when(meetingRecordQueryService.getRecord(PROJECT_ID, MEETING_ID, MEMBER_ID))
                .thenThrow(new CustomException(ProjectErrorCode.PROJECT_PARTICIPANT_NOT_FOUND));

        mockMvc.perform(get(URI, PROJECT_ID, MEETING_ID).session(loginSession()))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.status").value(404))
                .andExpect(jsonPath("$.errorCode").value("PROJECT_PARTICIPANT_NOT_FOUND"));
    }

    @DisplayName("회의가 요청한 프로젝트에 속하지 않으면 400을 반환한다.")
    @Test
    void returnsBadRequestWhenMeetingProjectMismatch() throws Exception {
        when(meetingRecordQueryService.getRecord(PROJECT_ID, MEETING_ID, MEMBER_ID))
                .thenThrow(new CustomException(MeetingErrorCode.MEETING_PROJECT_MISMATCH));

        mockMvc.perform(get(URI, PROJECT_ID, MEETING_ID).session(loginSession()))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("MEETING_PROJECT_MISMATCH"));
    }

    @DisplayName("로그인하지 않으면 401이고 Query Service를 호출하지 않는다.")
    @Test
    void rejectsAnonymousRequest() throws Exception {
        mockMvc.perform(get(URI, PROJECT_ID, MEETING_ID))
                .andExpect(status().isUnauthorized());

        verify(meetingRecordQueryService, never()).getRecord(anyInt(), anyInt(), anyInt());
    }

    @DisplayName("응답에 내부 식별자 commandId와 참여자 목록이 포함되지 않는다.")
    @Test
    void doesNotExposeCommandIdOrParticipants() throws Exception {
        when(meetingRecordQueryService.getRecord(PROJECT_ID, MEETING_ID, MEMBER_ID))
                .thenReturn(response());

        mockMvc.perform(get(URI, PROJECT_ID, MEETING_ID).session(loginSession()))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.commandId").doesNotExist())
                .andExpect(jsonPath("$.data.participants").doesNotExist());
    }

    private MeetingRecordDetailResponse response() {
        return new MeetingRecordDetailResponse(
                MEETING_RECORD_ID,
                PROJECT_ID,
                MEETING_ID,
                "AI 노드 구조 및 CI/CD 파이프라인 구축 방안 논의",
                STARTED_AT.toLocalDate(),
                STARTED_AT,
                ENDED_AT,
                91L,
                List.of("회의록 자동 생성 품질을 검토했습니다."),
                List.of("CI/CD 파이프라인을 단순화하기로 했습니다."),
                List.of("기술 용어 사전 목록을 설계합니다."),
                List.of("전문 용어 변환 오류가 있습니다."),
                0L,
                RECORD_CREATED_AT,
                RECORD_CREATED_AT
        );
    }

    private MockHttpSession loginSession() {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SessionConst.SESSION_LOGIN_MEMBER, LoginMember.builder()
                .id(MEMBER_ID)
                .name("member")
                .email("member@example.com")
                .build());
        return session;
    }
}
