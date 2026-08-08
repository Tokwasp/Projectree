package com.ssafy.projectree.domain.project.controller.dto.request;

import jakarta.validation.constraints.NotBlank;
import lombok.Builder;
import lombok.Getter;

@Getter
public class ProjectTitleUpdateRequest {
    @NotBlank
    private String title;

    @Builder
    private ProjectTitleUpdateRequest(String title) {
        this.title = title;
    }

    public ProjectTitleUpdateRequest() {}
}
