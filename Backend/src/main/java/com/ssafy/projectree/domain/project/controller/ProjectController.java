package com.ssafy.projectree.domain.project.controller;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.service.ProjectService;
import com.ssafy.projectree.global.response.ApiResponse;
import jakarta.servlet.http.HttpSession;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import static com.ssafy.projectree.global.config.session.SessionConst.SESSION_LOGIN_MEMBER;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/projects")
public class ProjectController {

    private final ProjectService projectService;

    @PostMapping
    public ResponseEntity<ApiResponse<Integer>> createProject(
            @Valid @RequestBody ProjectCreateRequest request, HttpSession session
    ) {
        LoginMember loginMember = (LoginMember) session.getAttribute(SESSION_LOGIN_MEMBER);
        if (loginMember == null) {
            throw new IllegalStateException("로그인이 필요합니다.");
        }
        Integer projectId = projectService.createProject(request, loginMember.getId());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(ApiResponse.success(projectId));
    }
}
