package com.ssafy.projectree.domain.project.controller.dto.request;

import jakarta.validation.constraints.NotBlank;
import lombok.Builder;
import lombok.Getter;

@Getter
public class ProjectContentUpdateRequest {
    @NotBlank
    private String content;

    @Builder
    private ProjectContentUpdateRequest(String content) {
        this.content = content;
    }

    public ProjectContentUpdateRequest(){}

}
