package com.ssafy.projectree.domain.notification.controller;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.notification.controller.request.NotificationCallbackRequest;
import com.ssafy.projectree.domain.notification.service.NotificationService;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@Tag(name = "notification")
@RestController
@RequestMapping("/api/notifications")
@RequiredArgsConstructor
public class NotificationController {

    private static final String LAST_EVENT_ID_HEADER = "Last-Event-ID";

    private final NotificationService notificationService;

    /**
     * 반환 타입이 ApiResponse 가 아니라 SseEmitter 다. 스트림이기 때문이다.
     * Last-Event-ID 는 첫 연결에는 없고 브라우저가 자동 재연결할 때만 붙는다.
     */
    @GetMapping(value = "/subscribe", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter subscribe(
            @Login LoginMember loginMember,
            @RequestHeader(value = LAST_EVENT_ID_HEADER, defaultValue = "") String lastEventId
    ) {
        return notificationService.subscribe(loginMember.getId(), lastEventId);
    }

    @PostMapping("/callback")
    public ResponseEntity<ApiResponse<Void>> callback(
            @Valid @RequestBody NotificationCallbackRequest request
    ) {
        notificationService.handleCallback(request);

        return ResponseEntity.ok(ApiResponse.success());
    }
}
