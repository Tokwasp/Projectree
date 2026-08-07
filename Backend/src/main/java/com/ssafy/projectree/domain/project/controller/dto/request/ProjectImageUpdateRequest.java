package com.ssafy.projectree.domain.project.controller.dto.request;

import jakarta.validation.constraints.NotBlank;
import lombok.Builder;
import lombok.Getter;

@Getter
public class ProjectImageUpdateRequest {

    @NotBlank
    private String imageURL;

    @Builder
    private ProjectImageUpdateRequest(String imageURL) {
        this.imageURL = imageURL;
    }

    public ProjectImageUpdateRequest(){};
}
