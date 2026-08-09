package com.ssafy.projectree.domain.meeting.record.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordUpdateRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordUpdateResponse;
import com.ssafy.projectree.domain.meeting.record.entity.MeetingRecord;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.config.session.SessionConst;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.orm.ObjectOptimisticLockingFailureException;

import java.time.LocalDateTime;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class MeetingRecordUpdateControllerTest extends ControllerTestSupport {

    private static final int PROJECT_ID = 3;
    private static final int MEETING_ID = 35;
    private static final int MEMBER_ID = 22;
    private static final String URI = "/api/projects/{projectId}/meetings/{meetingId}/record";

    @DisplayName("회의록 전체 수정에 성공하면 증가한 version과 수정 본문을 반환한다.")
    @Test
    void updatesRecord() throws Exception {
        MeetingRecordUpdateRequest request = validRequest();
        when(meetingRecordUpdateService.update(PROJECT_ID, MEETING_ID, MEMBER_ID, request))
                .thenReturn(new MeetingRecordUpdateResponse(
                        12L,
                        PROJECT_ID,
                        MEETING_ID,
                        request.title(),
                        request.summary(),
                        request.decisions(),
                        request.nextTodos(),
                        request.issues(),
                        1L,
                        LocalDateTime.of(2026, 8, 5, 17, 0)
                ));

        mockMvc.perform(put(URI, PROJECT_ID, MEETING_ID)
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.meetingRecordId").value(12))
                .andExpect(jsonPath("$.data.projectId").value(PROJECT_ID))
                .andExpect(jsonPath("$.data.meetingId").value(MEETING_ID))
                .andExpect(jsonPath("$.data.title").value("수정 제목"))
                .andExpect(jsonPath("$.data.summary[0]").value("요약"))
                .andExpect(jsonPath("$.data.decisions[0]").value("결정"))
                .andExpect(jsonPath("$.data.nextTodos[0]").value("할 일"))
                .andExpect(jsonPath("$.data.issues[0]").value("이슈"))
                .andExpect(jsonPath("$.data.version").value(1))
                .andExpect(jsonPath("$.data.updatedAt").value("2026-08-05T17:00:00"))
                .andExpect(jsonPath("$.data.commandId").doesNotExist())
                .andExpect(jsonPath("$.data.participants").doesNotExist())
                .andExpect(jsonPath("$.data.startedAt").doesNotExist());

        verify(meetingRecordUpdateService)
                .update(PROJECT_ID, MEETING_ID, MEMBER_ID, request);
    }

    @DisplayName("version을 생략하면 400이고 Service를 호출하지 않는다.")
    @Test
    void rejectsMissingVersion() throws Exception {
        mockMvc.perform(put(URI, PROJECT_ID, MEETING_ID)
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "title":"제목",
                                  "summary":[],
                                  "decisions":[],
                                  "nextTodos":[],
                                  "issues":[]
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        verify(meetingRecordUpdateService, never())
                .update(anyInt(), anyInt(), anyInt(), any());
    }

    @DisplayName("음수 version과 공백 본문 항목은 400이다.")
    @Test
    void rejectsInvalidBody() throws Exception {
        mockMvc.perform(put(URI, PROJECT_ID, MEETING_ID)
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "title":"제목",
                                  "summary":[" "],
                                  "decisions":[],
                                  "nextTodos":[],
                                  "issues":[],
                                  "version":-1
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));
    }

    @DisplayName("회의 생성자가 아니면 403을 반환한다.")
    @Test
    void returnsForbidden() throws Exception {
        when(meetingRecordUpdateService.update(anyInt(), anyInt(), anyInt(), any()))
                .thenThrow(new CustomException(
                        MeetingRecordErrorCode.MEETING_RECORD_UPDATE_FORBIDDEN
                ));

        performValidRequest()
                .andExpect(status().isForbidden())
                .andExpect(jsonPath("$.errorCode")
                        .value("MEETING_RECORD_UPDATE_FORBIDDEN"));
    }

    @DisplayName("stale version이면 409를 반환한다.")
    @Test
    void returnsVersionConflict() throws Exception {
        when(meetingRecordUpdateService.update(anyInt(), anyInt(), anyInt(), any()))
                .thenThrow(new CustomException(
                        MeetingRecordErrorCode.MEETING_RECORD_VERSION_CONFLICT
                ));

        performValidRequest()
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode")
                        .value("MEETING_RECORD_VERSION_CONFLICT"));
    }

    @DisplayName("JPA 낙관적 락 예외도 동일한 409 오류로 변환한다.")
    @Test
    void mapsOptimisticLockFailureToConflict() throws Exception {
        OptimisticLockingFailureException exception =
                new ObjectOptimisticLockingFailureException(MeetingRecord.class, 12L);
        when(meetingRecordUpdateService.update(anyInt(), anyInt(), anyInt(), any()))
                .thenThrow(exception);

        performValidRequest()
                .andExpect(status().isConflict())
                .andExpect(jsonPath("$.errorCode")
                        .value("MEETING_RECORD_VERSION_CONFLICT"));
    }

    @DisplayName("비로그인 요청은 401이고 Service를 호출하지 않는다.")
    @Test
    void rejectsAnonymousRequest() throws Exception {
        mockMvc.perform(put(URI, PROJECT_ID, MEETING_ID)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(validRequest())))
                .andExpect(status().isUnauthorized());

        verify(meetingRecordUpdateService, never())
                .update(anyInt(), anyInt(), anyInt(), any());
    }

    private org.springframework.test.web.servlet.ResultActions performValidRequest()
            throws Exception {
        return mockMvc.perform(put(URI, PROJECT_ID, MEETING_ID)
                .session(loginSession())
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(validRequest())));
    }

    private MeetingRecordUpdateRequest validRequest() {
        return new MeetingRecordUpdateRequest(
                "수정 제목",
                List.of("요약"),
                List.of("결정"),
                List.of("할 일"),
                List.of("이슈"),
                0L
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
