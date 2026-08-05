package com.ssafy.projectree.domain.meeting.record.controller;

import com.ssafy.projectree.domain.meeting.record.config.MeetingRecordCallbackAuthenticator;
import com.ssafy.projectree.domain.meeting.record.config.MeetingRecordCallbackConfig;
import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordCallbackRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordCallbackResponse;
import com.ssafy.projectree.domain.meeting.record.exception.MeetingRecordErrorCode;
import com.ssafy.projectree.domain.meeting.record.service.MeetingRecordCallbackService;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import tools.jackson.databind.ObjectMapper;

import java.util.List;
import java.util.UUID;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ActiveProfiles("test")
@Import({MeetingRecordCallbackConfig.class, MeetingRecordCallbackAuthenticator.class})
@TestPropertySource(properties = "app.meeting-record.callback.api-key=test-callback-key")
@WebMvcTest(controllers = InternalMeetingRecordCallbackController.class)
class MeetingRecordCallbackControllerTest {

    private static final int MEETING_ID = 35;
    private static final long MEETING_RECORD_ID = 91L;
    private static final UUID COMMAND_ID =
            UUID.fromString("0fcaeb2d-8f50-4ced-a081-54faf4de9f37");
    private static final String URI = "/api/internal/meetings/" + MEETING_ID + "/record";
    private static final String API_KEY_HEADER = "X-Internal-Api-Key";
    private static final String VALID_API_KEY = "test-callback-key";

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockitoBean
    private MeetingRecordCallbackService meetingRecordCallbackService;

    @DisplayName("올바른 API Key와 정상 본문은 200과 공통 응답 형식을 반환한다.")
    @Test
    void callbackSucceeds() throws Exception {
        MeetingRecordCallbackRequest request = validRequest();
        when(meetingRecordCallbackService.receive(MEETING_ID, request))
                .thenReturn(response(false));

        mockMvc.perform(put(URI)
                        .header(API_KEY_HEADER, VALID_API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data.meetingRecordId").value(MEETING_RECORD_ID))
                .andExpect(jsonPath("$.data.meetingId").value(MEETING_ID))
                .andExpect(jsonPath("$.data.commandId").value(COMMAND_ID.toString()))
                .andExpect(jsonPath("$.data.version").value(0))
                .andExpect(jsonPath("$.data.duplicated").value(false));

        verify(meetingRecordCallbackService).receive(MEETING_ID, request);
    }

    @DisplayName("동일 Callback 재시도도 200과 duplicated true를 반환한다.")
    @Test
    void duplicatedCallbackAlsoReturnsOk() throws Exception {
        when(meetingRecordCallbackService.receive(anyInt(), any()))
                .thenReturn(response(true));

        mockMvc.perform(put(URI)
                        .header(API_KEY_HEADER, VALID_API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(validRequest())))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.duplicated").value(true));
    }

    @DisplayName("Service가 던지는 CustomException은 ErrorCode의 상태와 이름으로 응답된다.")
    @ParameterizedTest
    @CsvSource({
            "MEETING_RECORD_SUMMARY_ALREADY_FAILED, 409",
            "MEETING_RECORD_CONTENT_TOO_LARGE, 400",
            "MEETING_RECORD_COMMAND_NOT_FOUND, 404",
            "MEETING_RECORD_COMMAND_MISMATCH, 409",
            "MEETING_RECORD_SUMMARY_NOT_REQUESTED, 409",
            "MEETING_RECORD_ALREADY_CREATED_BY_ANOTHER_COMMAND, 409"
    })
    void mapsServiceErrorsToStatus(MeetingRecordErrorCode errorCode, int expectedStatus)
            throws Exception {
        when(meetingRecordCallbackService.receive(anyInt(), any()))
                .thenThrow(new CustomException(errorCode));

        mockMvc.perform(put(URI)
                        .header(API_KEY_HEADER, VALID_API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(validRequest())))
                .andExpect(status().is(expectedStatus))
                .andExpect(jsonPath("$.status").value(expectedStatus))
                .andExpect(jsonPath("$.errorCode").value(errorCode.name()));
    }

    @DisplayName("인증 헤더가 없으면 401이고 Service를 호출하지 않는다.")
    @Test
    void rejectsMissingHeader() throws Exception {
        mockMvc.perform(put(URI)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(validRequest())))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401))
                .andExpect(jsonPath("$.errorCode")
                        .value("MEETING_RECORD_CALLBACK_UNAUTHORIZED"));

        verifyNoInteractions(meetingRecordCallbackService);
    }

    @DisplayName("빈 헤더나 잘못된 API Key는 401이고 Service를 호출하지 않는다.")
    @ParameterizedTest
    @ValueSource(strings = {"", " ", "wrong-callback-key", "test-callback-ke", "TEST-CALLBACK-KEY"})
    void rejectsBlankOrWrongApiKey(String apiKey) throws Exception {
        mockMvc.perform(put(URI)
                        .header(API_KEY_HEADER, apiKey)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(validRequest())))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.status").value(401));

        verifyNoInteractions(meetingRecordCallbackService);
    }

    @DisplayName("인증 실패 응답에 API Key가 노출되지 않는다.")
    @Test
    void doesNotLeakApiKeyInErrorResponse() throws Exception {
        String body = mockMvc.perform(put(URI)
                        .header(API_KEY_HEADER, "leaked-provided-key")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(validRequest())))
                .andExpect(status().isUnauthorized())
                .andReturn()
                .getResponse()
                .getContentAsString();

        org.assertj.core.api.Assertions.assertThat(body)
                .doesNotContain(VALID_API_KEY)
                .doesNotContain("leaked-provided-key");
    }

    @DisplayName("필수 필드가 누락되거나 형식이 잘못되면 400이고 Service를 호출하지 않는다.")
    @ParameterizedTest
    @ValueSource(strings = {
            // callbackSchemaVersion 누락
            """
            {"commandId":"0fcaeb2d-8f50-4ced-a081-54faf4de9f37","title":"제목",
             "summary":[],"decisions":[],"nextTodos":[],"issues":[]}
            """,
            // commandId 누락
            """
            {"callbackSchemaVersion":1,"title":"제목",
             "summary":[],"decisions":[],"nextTodos":[],"issues":[]}
            """,
            // commandId 형식 오류
            """
            {"callbackSchemaVersion":1,"commandId":"not-a-uuid","title":"제목",
             "summary":[],"decisions":[],"nextTodos":[],"issues":[]}
            """,
            // title 누락
            """
            {"callbackSchemaVersion":1,"commandId":"0fcaeb2d-8f50-4ced-a081-54faf4de9f37",
             "summary":[],"decisions":[],"nextTodos":[],"issues":[]}
            """,
            // title blank
            """
            {"callbackSchemaVersion":1,"commandId":"0fcaeb2d-8f50-4ced-a081-54faf4de9f37","title":"   ",
             "summary":[],"decisions":[],"nextTodos":[],"issues":[]}
            """,
            // summary null
            """
            {"callbackSchemaVersion":1,"commandId":"0fcaeb2d-8f50-4ced-a081-54faf4de9f37","title":"제목",
             "summary":null,"decisions":[],"nextTodos":[],"issues":[]}
            """,
            // decisions 누락
            """
            {"callbackSchemaVersion":1,"commandId":"0fcaeb2d-8f50-4ced-a081-54faf4de9f37","title":"제목",
             "summary":[],"nextTodos":[],"issues":[]}
            """,
            // nextTodos null
            """
            {"callbackSchemaVersion":1,"commandId":"0fcaeb2d-8f50-4ced-a081-54faf4de9f37","title":"제목",
             "summary":[],"decisions":[],"nextTodos":null,"issues":[]}
            """,
            // issues 누락
            """
            {"callbackSchemaVersion":1,"commandId":"0fcaeb2d-8f50-4ced-a081-54faf4de9f37","title":"제목",
             "summary":[],"decisions":[],"nextTodos":[]}
            """,
            // 배열 내부 null
            """
            {"callbackSchemaVersion":1,"commandId":"0fcaeb2d-8f50-4ced-a081-54faf4de9f37","title":"제목",
             "summary":["정상",null],"decisions":[],"nextTodos":[],"issues":[]}
            """,
            // 배열 내부 blank
            """
            {"callbackSchemaVersion":1,"commandId":"0fcaeb2d-8f50-4ced-a081-54faf4de9f37","title":"제목",
             "summary":["정상","  "],"decisions":[],"nextTodos":[],"issues":[]}
            """
    })
    void rejectsInvalidBody(String body) throws Exception {
        mockMvc.perform(put(URI)
                        .header(API_KEY_HEADER, VALID_API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(body))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value(400));

        verify(meetingRecordCallbackService, never()).receive(anyInt(), any());
    }

    @DisplayName("title이 200자를 넘으면 400이다.")
    @Test
    void rejectsTooLongTitle() throws Exception {
        MeetingRecordCallbackRequest request = new MeetingRecordCallbackRequest(
                1, COMMAND_ID, "가".repeat(201), List.of(), List.of(), List.of(), List.of()
        );

        mockMvc.perform(put(URI)
                        .header(API_KEY_HEADER, VALID_API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isBadRequest());

        verify(meetingRecordCallbackService, never()).receive(anyInt(), any());
    }

    @DisplayName("네 배열이 모두 비어 있어도 유효한 요청이다.")
    @Test
    void acceptsEmptyArrays() throws Exception {
        MeetingRecordCallbackRequest request = new MeetingRecordCallbackRequest(
                1, COMMAND_ID, "제목", List.of(), List.of(), List.of(), List.of()
        );
        when(meetingRecordCallbackService.receive(eq(MEETING_ID), any()))
                .thenReturn(response(false));

        mockMvc.perform(put(URI)
                        .header(API_KEY_HEADER, VALID_API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());

        verify(meetingRecordCallbackService).receive(MEETING_ID, request);
    }

    @DisplayName("배열 항목 순서는 Service까지 그대로 전달된다.")
    @Test
    void preservesArrayOrder() throws Exception {
        MeetingRecordCallbackRequest request = new MeetingRecordCallbackRequest(
                1,
                COMMAND_ID,
                "제목",
                List.of("요약 1", "요약 2", "요약 3"),
                List.of("결정 1"),
                List.of("할 일 1"),
                List.of("이슈 1")
        );
        when(meetingRecordCallbackService.receive(eq(MEETING_ID), any()))
                .thenReturn(response(false));

        mockMvc.perform(put(URI)
                        .header(API_KEY_HEADER, VALID_API_KEY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(objectMapper.writeValueAsString(request)))
                .andExpect(status().isOk());

        verify(meetingRecordCallbackService).receive(MEETING_ID, request);
    }

    private MeetingRecordCallbackRequest validRequest() {
        return new MeetingRecordCallbackRequest(
                1,
                COMMAND_ID,
                "AI 노드 구조 및 CI/CD 파이프라인 구축 방안 논의",
                List.of("첫 번째 전체 요약", "두 번째 전체 요약"),
                List.of("첫 번째 결정 사항"),
                List.of("첫 번째 다음 할 일"),
                List.of("첫 번째 이슈")
        );
    }

    private MeetingRecordCallbackResponse response(boolean duplicated) {
        return new MeetingRecordCallbackResponse(
                MEETING_RECORD_ID, MEETING_ID, COMMAND_ID, 0L, duplicated
        );
    }
}
