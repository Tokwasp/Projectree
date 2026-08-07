package com.ssafy.projectree.domain.project.controller;

import com.ssafy.projectree.domain.member.LoginMember;
import com.ssafy.projectree.domain.project.controller.dto.request.ProjectContentUpdateRequest;
import com.ssafy.projectree.domain.project.controller.dto.request.ProjectImageUpdateRequest;
import com.ssafy.projectree.domain.project.controller.dto.request.ProjectTitleUpdateRequest;
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

    @PutMapping(value = "/{projectId}/image")
    public ResponseEntity<ApiResponse<Void>> updateImage(@PathVariable("projectId") int projectId,
                                                         @RequestBody ProjectImageUpdateRequest request,
                                                         @Login LoginMember loginMember) {
        projectService.updateImage(projectId, loginMember.getId(), request.getImageURL());
        return ResponseEntity.ok(ApiResponse.success());
    }

    @PutMapping("/{projectId}/title")
    public ResponseEntity<ApiResponse<Void>> updateTitle(@PathVariable("projectId") int projectId,
                                                         @RequestBody ProjectTitleUpdateRequest request,
                                                         @Login LoginMember loginMember) {
        projectService.updateTitle(projectId, loginMember.getId(), request.getTitle());
        return ResponseEntity.ok(ApiResponse.success());
    }

    @PutMapping("/{projectId}/content")
    public ResponseEntity<ApiResponse<Void>> updateContent(@PathVariable("projectId") int projectId,
                                                           @RequestBody ProjectContentUpdateRequest request,
                                                           @Login LoginMember loginMember) {
        projectService.updateContent(projectId, loginMember.getId(), request.getContent());
        return ResponseEntity.ok(ApiResponse.success());
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
