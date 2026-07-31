package com.ssafy.projectree.domain.project.dto.response;

import lombok.Getter;

import java.util.List;

@Getter
public class ProjectMemberListResponse {

    private final List<ProjectMemberResponse> members;

    public ProjectMemberListResponse(List<ProjectMemberResponse> members) {
        this.members = members;
    }
}
