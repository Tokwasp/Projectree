package com.ssafy.projectree.domain.meeting.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.meeting.dto.request.MeetingAnalysisRequest;
import com.ssafy.projectree.domain.meeting.dto.response.MeetingAnalysisRequestResponse;
import com.ssafy.projectree.domain.meeting.entity.AnalysisTaskStatus;
import com.ssafy.projectree.domain.meeting.exception.MeetingErrorCode;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;

import java.util.UUID;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class MeetingControllerTest extends ControllerTestSupport {

    private static final int PROJECT_ID = 15;
    private static final int MEMBER_ID = 7;
    private static final int MEETING_ID = 35;
    private static final String ROOM_NAME = "c6db7ac7-d3c7-4f18-928c-ce376ccfabba";
    private static final UUID COMMAND_ID =
            UUID.fromString("550e8400-e29b-41d4-a716-446655440000");
    private static final String URI =
            "/api/projects/" + PROJECT_ID + "/meetings/" + ROOM_NAME + "/analysis-request";

    @DisplayName("PUT 분석 요청은 로그인 사용자 ID를 전달하고 202 응답을 반환한다.")
    @Test
    void requestAnalysis() throws Exception {
        MeetingAnalysisRequest request = new MeetingAnalysisRequest(true, false);
        when(meetingAnalysisRequestService.requestAnalysis(
                PROJECT_ID, ROOM_NAME, MEMBER_ID, request
        )).thenReturn(response(true, false));

        mockMvc.perform(put(URI)
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isAccepted())
                .andExpect(jsonPath("$.status").value(202))
                .andExpect(jsonPath("$.data.meetingId").value(MEETING_ID))
                .andExpect(jsonPath("$.data.projectId").value(PROJECT_ID))
                .andExpect(jsonPath("$.data.roomName").value(ROOM_NAME))
                .andExpect(jsonPath("$.data.generateSummary").value(true))
                .andExpect(jsonPath("$.data.summaryStatus").value("PROCESSING"))
                .andExpect(jsonPath("$.data.generateNodes").value(false))
                .andExpect(jsonPath("$.data.nodeStatus").value("SKIPPED"))
                .andExpect(jsonPath("$.data.commandId").value(COMMAND_ID.toString()));

        verify(meetingAnalysisRequestService)
                .requestAnalysis(PROJECT_ID, ROOM_NAME, MEMBER_ID, request);
    }

    @DisplayName("모든 분석 작업 선택 Boolean 조합은 유효하다.")
    @ParameterizedTest
    @ValueSource(strings = {
            "{\"generateSummary\":true,\"generateNodes\":true}",
            "{\"generateSummary\":true,\"generateNodes\":false}",
            "{\"generateSummary\":false,\"generateNodes\":true}",
            "{\"generateSummary\":false,\"generateNodes\":false}"
    })
    void acceptsSelectedTaskCombinations(String body) throws Exception {
        when(meetingAnalysisRequestService.requestAnalysis(
                eq(PROJECT_ID), eq(ROOM_NAME), eq(MEMBER_ID), any(MeetingAnalysisRequest.class)
        )).thenReturn(response(false, false));

        mockMvc.perform(put(URI)
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isAccepted());
    }

    @DisplayName("필수 Boolean 필드가 누락되거나 null이면 400을 반환한다.")
    @ParameterizedTest
    @ValueSource(strings = {
            "{\"generateNodes\":true}",
            "{\"generateSummary\":true}",
            "{\"generateSummary\":null,\"generateNodes\":true}",
            "{\"generateSummary\":true,\"generateNodes\":null}"
    })
    void rejectsMissingOrNullBoolean(String body) throws Exception {
        mockMvc.perform(put(URI)
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest());

        verify(meetingAnalysisRequestService, never())
                .requestAnalysis(any(Integer.class), any(), any(Integer.class), any());
    }

    @DisplayName("canonical UUID가 아닌 roomName은 400을 반환한다.")
    @ParameterizedTest
    @ValueSource(strings = {"1-1-1-1-1", "not-a-uuid", "550e8400e29b41d4a716446655440000"})
    void rejectsInvalidRoomName(String invalidRoomName) throws Exception {
        String uri = "/api/projects/" + PROJECT_ID
                + "/meetings/" + invalidRoomName + "/analysis-request";
        MeetingAnalysisRequest request = new MeetingAnalysisRequest(true, false);
        when(meetingAnalysisRequestService.requestAnalysis(
                PROJECT_ID, invalidRoomName, MEMBER_ID, request
        )).thenThrow(new CustomException(MeetingErrorCode.INVALID_ROOM_NAME));

        mockMvc.perform(put(uri)
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());
    }

    @DisplayName("서비스의 권한·조회·중복 오류를 각각 403, 404, 409로 반환한다.")
    @ParameterizedTest
    @ValueSource(strings = {
            "MEETING_ACCESS_DENIED",
            "MEETING_NOT_FOUND",
            "MEETING_ANALYSIS_ALREADY_REQUESTED"
    })
    void mapsBusinessErrors(String errorName) throws Exception {
        MeetingErrorCode errorCode = MeetingErrorCode.valueOf(errorName);
        MeetingAnalysisRequest request = new MeetingAnalysisRequest(true, false);
        when(meetingAnalysisRequestService.requestAnalysis(
                PROJECT_ID, ROOM_NAME, MEMBER_ID, request
        )).thenThrow(new CustomException(errorCode));

        mockMvc.perform(put(URI)
                        .session(loginSession())
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().is(errorCode.getStatus().value()));
    }

    @DisplayName("로그인 세션이 없으면 401을 반환한다.")
    @Test
    void requiresLogin() throws Exception {
        mockMvc.perform(put(URI)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"generateSummary\":true,\"generateNodes\":false}"))
                .andExpect(status().isUnauthorized());
    }

    private MeetingAnalysisRequestResponse response(
            boolean generateSummary,
            boolean generateNodes
    ) {
        return new MeetingAnalysisRequestResponse(
                MEETING_ID,
                PROJECT_ID,
                ROOM_NAME,
                generateSummary,
                generateSummary ? AnalysisTaskStatus.PROCESSING : AnalysisTaskStatus.SKIPPED,
                generateNodes,
                generateNodes ? AnalysisTaskStatus.PROCESSING : AnalysisTaskStatus.SKIPPED,
                COMMAND_ID
        );
    }

    private MockHttpSession loginSession() {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(
                SESSION_LOGIN_MEMBER,
                LoginMember.builder()
                        .id(MEMBER_ID)
                        .name("member")
                        .email("member@example.com")
                        .build()
        );
        return session;
    }
}
