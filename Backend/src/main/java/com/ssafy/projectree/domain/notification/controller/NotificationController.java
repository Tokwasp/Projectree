package com.ssafy.projectree.domain.notification.controller;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.notification.controller.request.NotificationCallbackRequest;
import com.ssafy.projectree.domain.notification.service.NotificationService;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

@RestController
@RequestMapping("/api/notifications")
@RequiredArgsConstructor
public class NotificationController {

    private final NotificationService notificationService;

    @GetMapping(value = "/subscribe", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter subscribe(@Login LoginMember loginMember,
                                @RequestHeader(value = "Last-Event-ID", defaultValue = "") String lastEventId) {
        return notificationService.subscribe(loginMember.getId(), lastEventId);
    }

    @PostMapping("/callback")
    public ResponseEntity<ApiResponse<Void>> callback(@Valid @RequestBody NotificationCallbackRequest request) {
        notificationService.handleCallback(request);
        return ResponseEntity.ok(ApiResponse.success());
    }
}
