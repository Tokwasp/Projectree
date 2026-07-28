package com.ssafy.projectree.domain.project.dto.request;

import jakarta.validation.constraints.*;
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
}
