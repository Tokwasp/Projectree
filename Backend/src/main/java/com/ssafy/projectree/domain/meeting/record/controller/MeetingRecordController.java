package com.ssafy.projectree.domain.meeting.record.controller;

import com.ssafy.projectree.domain.meeting.record.dto.request.MeetingRecordUpdateRequest;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordDetailResponse;
import com.ssafy.projectree.domain.meeting.record.dto.response.MeetingRecordUpdateResponse;
import com.ssafy.projectree.domain.meeting.record.service.MeetingRecordQueryService;
import com.ssafy.projectree.domain.meeting.record.service.MeetingRecordUpdateService;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Tag(name = "meeting_record")
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/projects/{projectId}/meetings")
public class MeetingRecordController {

    private final MeetingRecordQueryService meetingRecordQueryService;
    private final MeetingRecordUpdateService meetingRecordUpdateService;

    @Operation(summary = "회의록 상세 조회")
    @GetMapping("/{meetingId}/record")
    public ResponseEntity<ApiResponse<MeetingRecordDetailResponse>> getRecord(
            @PathVariable int projectId,
            @PathVariable int meetingId,
            @Login LoginMember loginMember
    ) {
        MeetingRecordDetailResponse response = meetingRecordQueryService.getRecord(
                projectId,
                meetingId,
                loginMember.getId()
        );

        return ResponseEntity.ok(ApiResponse.success(response));
    }

    @Operation(summary = "회의록 전체 수정")
    @PutMapping("/{meetingId}/record")
    public ResponseEntity<ApiResponse<MeetingRecordUpdateResponse>> updateRecord(
            @PathVariable int projectId,
            @PathVariable int meetingId,
            @Login LoginMember loginMember,
            @Valid @RequestBody MeetingRecordUpdateRequest request
    ) {
        MeetingRecordUpdateResponse response = meetingRecordUpdateService.update(
                projectId,
                meetingId,
                loginMember.getId(),
                request
        );
        return ResponseEntity.ok(ApiResponse.success(response));
    }
}
