package com.ssafy.projectree.domain.meeting.controller;

import com.ssafy.projectree.domain.meeting.dto.request.MeetingAnalysisRequest;
import com.ssafy.projectree.domain.meeting.dto.response.MeetingAnalysisRequestResponse;
import com.ssafy.projectree.domain.meeting.service.MeetingAnalysisRequestService;
import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/projects/{projectId}/meetings")
public class MeetingController {

    private final MeetingAnalysisRequestService meetingAnalysisRequestService;

    @PutMapping("/{roomName}/analysis-request")
    public ResponseEntity<ApiResponse<MeetingAnalysisRequestResponse>> requestAnalysis(
            @PathVariable int projectId,
            @PathVariable String roomName,
            @Valid @RequestBody MeetingAnalysisRequest request,
            @Login LoginMember loginMember
    ) {
        MeetingAnalysisRequestResponse response = meetingAnalysisRequestService.requestAnalysis(
                projectId,
                roomName,
                loginMember.getId(),
                request
        );

        return ResponseEntity
                .status(HttpStatus.ACCEPTED)
                .body(ApiResponse.accepted(response));
    }
}
