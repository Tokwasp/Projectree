package com.ssafy.projectree.domain.notification.controller;

import com.ssafy.projectree.ControllerTestSupport;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.notification.controller.request.NotificationCallbackRequest;
import com.ssafy.projectree.domain.notification.entity.NotificationType;
import com.ssafy.projectree.global.exception.CommonErrorCode;
import com.ssafy.projectree.global.exception.CustomException;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.BDDMockito.given;
import static org.mockito.BDDMockito.then;
import static org.mockito.BDDMockito.willThrow;
import static org.mockito.Mockito.never;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class NotificationControllerTest extends ControllerTestSupport {

    private static final int MEMBER_ID = 7;

    @DisplayName("로그인 세션으로 구독하면 끊기지 않는 이벤트 스트림이 열린다.")
    @Test
    void subscribe() throws Exception {
        // given
        given(notificationService.subscribe(anyInt(), any())).willReturn(new SseEmitter());

        // when // then
        mockMvc.perform(get("/api/notifications/subscribe")
                        .session(loginSession(MEMBER_ID)))
                .andExpect(status().isOk())
                .andExpect(request().asyncStarted())
                .andExpect(content().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM));
    }

    @DisplayName("로그인 세션이 없으면 401을 응답한다.")
    @Test
    void subscribeWithoutSession() throws Exception {
        // when // then
        mockMvc.perform(get("/api/notifications/subscribe"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.errorCode").value("UNAUTHORIZED"));

        then(notificationService).should(never()).subscribe(anyInt(), any());
    }

    @DisplayName("재연결 시 브라우저가 붙인 Last-Event-ID 를 그대로 넘긴다.")
    @Test
    void subscribeWithLastEventId() throws Exception {
        // given
        given(notificationService.subscribe(anyInt(), any())).willReturn(new SseEmitter());

        // when // then
        mockMvc.perform(get("/api/notifications/subscribe")
                        .session(loginSession(MEMBER_ID))
                        .header("Last-Event-ID", "41"))
                .andExpect(status().isOk());

        then(notificationService).should().subscribe(MEMBER_ID, 41);
    }

    @DisplayName("Last-Event-ID 는 첫 연결에 없으므로 없어도 구독할 수 있다.")
    @Test
    void subscribeWithoutLastEventId() throws Exception {
        // given
        given(notificationService.subscribe(anyInt(), any())).willReturn(new SseEmitter());

        // when // then
        mockMvc.perform(get("/api/notifications/subscribe")
                        .session(loginSession(MEMBER_ID)))
                .andExpect(status().isOk());

        then(notificationService).should().subscribe(MEMBER_ID, null);
    }

    @DisplayName("숫자가 아닌 Last-Event-ID 로는 구독할 수 없다.")
    @Test
    void subscribeWithNonNumericLastEventId() throws Exception {
        // when // then
        mockMvc.perform(get("/api/notifications/subscribe")
                        .session(loginSession(MEMBER_ID))
                        .header("Last-Event-ID", "abc"))
                .andExpect(status().isBadRequest());

        then(notificationService).should(never()).subscribe(anyInt(), any());
    }

    @DisplayName("AI 서버가 작업 완료를 콜백하면 200을 응답한다.")
    @Test
    void callback() throws Exception {
        // when // then
        mockMvc.perform(post("/api/notifications/callback")
                        .content(objectMapper.writeValueAsString(
                                callbackRequest(NotificationType.TREE_CREATED, MEMBER_ID)))
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value(200))
                .andExpect(jsonPath("$.message").value("성공"))
                .andExpect(jsonPath("$.data").isEmpty());
    }

    @DisplayName("콜백은 세션 없이 호출할 수 있다.")
    @Test
    void callbackWithoutSession() throws Exception {
        // when // then
        mockMvc.perform(post("/api/notifications/callback")
                        .content(objectMapper.writeValueAsString(
                                callbackRequest(NotificationType.TREE_CREATED, MEMBER_ID)))
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isOk());

        then(notificationService).should().handleCallback(any(NotificationCallbackRequest.class));
    }

    @DisplayName("콜백에 알림 타입이 없으면 400을 응답한다.")
    @Test
    void callbackWithoutType() throws Exception {
        // when // then
        mockMvc.perform(post("/api/notifications/callback")
                        .content(objectMapper.writeValueAsString(callbackRequest(null, MEMBER_ID)))
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(notificationService).should(never()).handleCallback(any(NotificationCallbackRequest.class));
    }

    @DisplayName("정의되지 않은 알림 타입을 보내면 400을 응답한다.")
    @Test
    void callbackWithUnknownType() throws Exception {
        // when // then
        mockMvc.perform(post("/api/notifications/callback")
                        .content("""
                                {"type":"UNKNOWN","receiverId":7}
                                """)
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(notificationService).should(never()).handleCallback(any(NotificationCallbackRequest.class));
    }

    @DisplayName("콜백의 수신자 id 는 양수여야 한다.")
    @Test
    void callbackWithZeroReceiverId() throws Exception {
        // when // then
        mockMvc.perform(post("/api/notifications/callback")
                        .content(objectMapper.writeValueAsString(
                                callbackRequest(NotificationType.TREE_CREATED, 0)))
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.errorCode").value("INVALID_REQUEST"));

        then(notificationService).should(never()).handleCallback(any(NotificationCallbackRequest.class));
    }

    @DisplayName("존재하지 않는 회원에게 보내는 콜백은 404를 응답한다.")
    @Test
    void callbackWithUnknownReceiver() throws Exception {
        // given
        willThrow(new CustomException(CommonErrorCode.MEMBER_NOT_FOUND))
                .given(notificationService).handleCallback(any(NotificationCallbackRequest.class));

        // when // then
        mockMvc.perform(post("/api/notifications/callback")
                        .content(objectMapper.writeValueAsString(
                                callbackRequest(NotificationType.TREE_CREATED, 999)))
                        .contentType(MediaType.APPLICATION_JSON))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.errorCode").value("MEMBER_NOT_FOUND"));
    }

    private NotificationCallbackRequest callbackRequest(NotificationType type, int receiverId) {
        return NotificationCallbackRequest.builder()
                .type(type)
                .receiverId(receiverId)
                .build();
    }

    private MockHttpSession loginSession(int memberId) {
        MockHttpSession session = new MockHttpSession();
        session.setAttribute(SESSION_LOGIN_MEMBER, LoginMember.builder()
                .id(memberId)
                .name("김싸피")
                .email("ssafy@gmail.com")
                .build());

        return session;
    }
}
