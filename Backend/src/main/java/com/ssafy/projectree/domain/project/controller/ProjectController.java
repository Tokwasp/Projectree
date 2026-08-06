package com.ssafy.projectree.domain.project.controller;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.project.controller.dto.response.home.ProjectHomeResponse;
import com.ssafy.projectree.domain.project.dto.request.ProjectCreateRequest;
import com.ssafy.projectree.domain.project.dto.response.ProjectListResponse;
import com.ssafy.projectree.domain.project.dto.response.ProjectMemberListResponse;
import com.ssafy.projectree.domain.project.dto.response.ProjectMemberResponse;
import com.ssafy.projectree.domain.project.service.ProjectService;
import com.ssafy.projectree.global.annotation.Login;
import com.ssafy.projectree.global.response.ApiResponse;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/projects")
public class ProjectController {

    private final ProjectService projectService;

    @PostMapping
    public ResponseEntity<ApiResponse<Integer>> createProject(
            @Valid @RequestBody ProjectCreateRequest request,
            @Login LoginMember loginMember
    ) {

        Integer projectId =
                projectService.createProject(request, loginMember.getId());

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(ApiResponse.success(projectId));
    }

    @DeleteMapping("/{projectId}")
    public ResponseEntity<ApiResponse<Void>> deleteProject(
            @PathVariable int projectId,
            @Login LoginMember loginMember
    ) {

        projectService.deleteProject(projectId, loginMember.getId());

        return ResponseEntity.ok(ApiResponse.success());
    }

    @DeleteMapping("/{projectId}/members/me")
    public ResponseEntity<ApiResponse<Void>> leaveProject(
            @PathVariable int projectId,
            @Login LoginMember loginMember
    ) {

        projectService.leaveProject(projectId, loginMember.getId());

        return ResponseEntity.ok(ApiResponse.success());
    }

    @GetMapping("/{projectId}/members")
    public ResponseEntity<ApiResponse<ProjectMemberListResponse>> getProjectMembers(
            @PathVariable int projectId,
            @Login LoginMember loginMember
    ) {

        List<ProjectMemberResponse> members = projectService.getProjectMembers(projectId, loginMember.getId());

        return ResponseEntity.ok(ApiResponse.success(new ProjectMemberListResponse(members)));
    }

    @GetMapping
    public ResponseEntity<ApiResponse<ProjectListResponse>> getProjectList(
            @PageableDefault(size = 10, sort = {"createdAt", "id"}, direction = Sort.Direction.DESC)
            Pageable pageable,
            @Login LoginMember loginMember
    ) {

        ProjectListResponse projectList = projectService.getProjectList(pageable, loginMember.getId());

        return ResponseEntity.ok(ApiResponse.success(projectList));
    }

    @GetMapping("/{project-id}/home")
    public ResponseEntity<ApiResponse<ProjectHomeResponse>> getProjectHome(
            @PathVariable("project-id") int projectId,
            @Login LoginMember loginMember
    ) {
        ProjectHomeResponse response = projectService.getProjectHome(projectId, loginMember.getId());
        return ResponseEntity.ok(ApiResponse.success(response));
    }
}
