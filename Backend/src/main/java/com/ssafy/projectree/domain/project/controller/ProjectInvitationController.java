package com.ssafy.projectree.domain.project.controller;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.project.controller.dto.request.InvitationCreateRequest;
import com.ssafy.projectree.domain.project.controller.dto.response.InviteResultsResponse;
import com.ssafy.projectree.domain.project.controller.dto.response.PendingInvitationResponse;
import com.ssafy.projectree.domain.project.service.ProjectInvitationService;
import com.ssafy.projectree.domain.project.service.result.PendingInvitation;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.List;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/projects/{projectId}/invitations")
public class ProjectInvitationController {

    private final ProjectInvitationService projectInvitationService;

    @PostMapping
    public ResponseEntity<ApiResponse<InviteResultsResponse>> invite(
            @PathVariable int projectId,
            @Valid @RequestBody InvitationCreateRequest request,
            @Login LoginMember loginMember
    ) {
        InviteResultsResponse response = InviteResultsResponse.from(projectInvitationService.invite(
                projectId, loginMember.getId(), request.getInviteeMemberIds()
        ));
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    @GetMapping
    public ResponseEntity<ApiResponse<List<PendingInvitationResponse>>> getPendingInvitations(
            @PathVariable int projectId,
            @Login LoginMember loginMember
    ) {
        List<PendingInvitationResponse> response = projectInvitationService
                .getPendingInvitations(projectId, loginMember.getId())
                .stream()
                .map(PendingInvitationResponse::from)
                .toList();
        return ResponseEntity.ok(ApiResponse.success(response));
    }

    @DeleteMapping("/{invitationId}")
    public ResponseEntity<Void> cancelInvitation(
            @PathVariable int projectId,
            @PathVariable int invitationId,
            @Login LoginMember loginMember
    ) {
        projectInvitationService.cancelInvitation(projectId, invitationId, loginMember.getId());
        return ResponseEntity.noContent().build();
    }
}
