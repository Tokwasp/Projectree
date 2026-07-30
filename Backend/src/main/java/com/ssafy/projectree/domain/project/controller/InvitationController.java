package com.ssafy.projectree.domain.project.controller;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.project.controller.dto.response.InvitationAcceptResponse;
import com.ssafy.projectree.domain.project.controller.dto.response.InvitationLandingResponse;
import com.ssafy.projectree.domain.project.service.ProjectInvitationService;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/invitations")
public class InvitationController {

    private final ProjectInvitationService projectInvitationService;

    @GetMapping("/{token}")
    public ResponseEntity<ApiResponse<InvitationLandingResponse>> getLanding(
            @PathVariable String token,
            @Login LoginMember loginMember
    ) {
        InvitationLandingResponse response = InvitationLandingResponse.from(
                projectInvitationService.getLanding(token, loginMember.getId())
        );
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    @PostMapping("/{token}/accept")
    public ResponseEntity<ApiResponse<InvitationAcceptResponse>> acceptInvitation(
            @PathVariable String token,
            @Login LoginMember loginMember
    ) {
        InvitationAcceptResponse response = InvitationAcceptResponse.of(
                projectInvitationService.acceptInvitation(token, loginMember.getId())
        );
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    @PostMapping("/{token}/reject")
    public ResponseEntity<Void> rejectInvitation(
            @PathVariable String token,
            @Login LoginMember loginMember
    ) {
        projectInvitationService.rejectInvitation(token, loginMember.getId());
        return ResponseEntity.noContent().build();
    }
}
