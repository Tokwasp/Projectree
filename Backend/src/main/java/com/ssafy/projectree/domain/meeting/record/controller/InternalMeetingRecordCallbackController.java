package com.ssafy.projectree.domain.meeting.record.controller;

import com.ssafy.projectree.domain.meeting.record.config.MeetingRecordCallbackAuthenticator;
import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordCallbackRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordCallbackResponse;
import com.ssafy.projectree.domain.meeting.record.service.MeetingRecordCallbackService;
import com.ssafy.projectree.global.response.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Python 분석 서버 전용 내부 Callback.
 * 사용자 세션 대신 공유 비밀 헤더로 인증하므로 @Login을 사용하지 않는다.
 */
@Tag(name = "internal_meeting_record")
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/internal/meetings")
public class InternalMeetingRecordCallbackController {

    private static final String INTERNAL_API_KEY_HEADER = "X-Internal-Api-Key";

    private final MeetingRecordCallbackAuthenticator authenticator;
    private final MeetingRecordCallbackService meetingRecordCallbackService;

    @Operation(summary = "회의록 최초 생성 Callback")
    @PutMapping("/{meetingId}/record")
    public ResponseEntity<ApiResponse<MeetingRecordCallbackResponse>> callback(
            @PathVariable int meetingId,
            @RequestHeader(name = INTERNAL_API_KEY_HEADER, required = false) String apiKey,
            @Valid @RequestBody MeetingRecordCallbackRequest request
    ) {
        authenticator.authenticate(apiKey);

        MeetingRecordCallbackResponse response =
                meetingRecordCallbackService.receive(meetingId, request);

        return ResponseEntity.ok(ApiResponse.success(response));
    }
}
