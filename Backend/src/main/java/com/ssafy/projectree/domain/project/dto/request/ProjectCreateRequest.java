package com.ssafy.projectree.domain.project.dto.request;

import com.ssafy.projectree.domain.project.entity.Project;
import jakarta.validation.constraints.*;
import lombok.Builder;
import lombok.Getter;

@Getter
public class ProjectCreateRequest {

    @NotBlank(message = "프로젝트 제목은 필수입니다.")
    @Size(max = 100, message = "제목은 100자를 넘을 수 없습니다.")
    private String title;

    @NotBlank(message = "프로젝트 설명은 필수입니다.")
    @Size(max = 200, message = "설명은 200자를 넘을 수 없습니다.")
    private String content;

    @Size(max = 1024, message = "이미지 URL이 너무 깁니다.")
    private String photoUrl;

    private ProjectCreateRequest() {
    }

    @Builder
    private ProjectCreateRequest(String title, String content, String photoUrl) {
        this.title = title;
        this.content = content;
        this.photoUrl = photoUrl;
    }

    public Project toEntity() {
        return Project.builder()
                .title(title)
                .content(content)
                .photoUrl(photoUrl)
                .build();
    }
}
