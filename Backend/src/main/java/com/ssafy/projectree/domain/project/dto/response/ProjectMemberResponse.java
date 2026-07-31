package com.ssafy.projectree.domain.project.dto.response;

import com.ssafy.projectree.domain.project.entity.ProjectRole;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
public class ProjectMemberResponse {

    private final int memberId;
    private final String name;
    private final String email;
    private final ProjectRole role;
    private final LocalDateTime joinedAt;


    public ProjectMemberResponse(int memberId, String name, String email, ProjectRole role, LocalDateTime joinedAt) {
        this.memberId = memberId;
        this.name = name;
        this.email = email;
        this.role = role;
        this.joinedAt = joinedAt;
    }
}
